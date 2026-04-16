from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, exists, String
from typing import List, Optional
from uuid import UUID
import datetime

from app.db.db_session import get_db_session
from app.services.signup_service.auth import check_access_token
from app.models.meeting import Meeting
from app.models.meeting_user import MeetingUser
from app.models.calendar import Calendar
from app.models.flowy_user import FlowyUser
from app.schemas.meeting import (
    PendingMeetingResponse,
    AcceptMeetingRequest,
    RejectMeetingRequest,
    MeetingActionResponse,
    MeetingPromptLogsByMeetingResponse,
    MeetingPromptLogsResponse,
)
from app.schemas.signup_info import TokenPayload
from app.crud.crud_meeting import get_prompt_logs_by_meeting, get_all_prompt_logs
from app.services.calendar_service.calendar_crud import insert_meeting_calendar

router = APIRouter()

# PO 권한 체크 함수
async def check_po_permission(db: AsyncSession, user_id: UUID, meeting_id: UUID) -> bool:
    """사용자가 해당 회의의 PO(호스트)인지 확인"""
    HOST_ROLE_ID = "20ea65e2-d3b7-4adb-a8ce-9e67a2f21999"
    
    stmt = select(MeetingUser).where(
        and_(
            MeetingUser.user_id == user_id,
            MeetingUser.meeting_id == meeting_id,
            MeetingUser.role_id == HOST_ROLE_ID
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None

@router.get(
    "/pending",
    response_model=List[PendingMeetingResponse],
    summary="확인 대기 예정 회의 조회",
    description="현재 회의를 기준으로 PO 권한 사용자가 확인해야 하는 후속 예정 회의 목록을 조회합니다.",
)
async def get_pending_meetings(
    request: Request,
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: TokenPayload = Depends(check_access_token)
):
    """
    1️⃣ 확인 대기 중인 예정 회의 조회 API
    
    현재 meeting_id와 같은 프로젝트에서
    - meeting_audio_path = 'app/none' (Agent 생성)
    - 현재 사용자가 PO 권한
    - calendar 테이블에 agent_meeting_id가 없는 것 조회
    """
    try:
        user_id = UUID(current_user.id)
        
        # 현재 회의의 프로젝트 ID 조회
        current_meeting_stmt = select(Meeting.project_id).where(Meeting.meeting_id == meeting_id)
        current_meeting_result = await db.execute(current_meeting_stmt)
        current_meeting = current_meeting_result.scalar_one_or_none()
        
        if not current_meeting:
            raise HTTPException(status_code=404, detail="현재 회의를 찾을 수 없습니다.")
        
        project_id = current_meeting
        
        # PO 권한 체크
        is_po = await check_po_permission(db, user_id, meeting_id)
        if not is_po:
            raise HTTPException(status_code=403, detail="PO 권한이 필요합니다.")
        
        # 확인 대기 중인 예정 회의 조회
        # 1. Agent가 생성한 회의 (meeting_audio_path = 'app/none')
        # 2. 현재 사용자가 PO인 회의만
        # 3. 아직 캘린더에 처리되지 않은 것 (calendar.agent_meeting_id로 현재 회의 ID가 등록되지 않은 것)
        HOST_ROLE_ID = "20ea65e2-d3b7-4adb-a8ce-9e67a2f21999"
        
        stmt = select(Meeting).join(
            MeetingUser, Meeting.meeting_id == MeetingUser.meeting_id
        ).where(
            and_(
                Meeting.meeting_audio_path == 'app/none',
                Meeting.parent_meeting_id == str(meeting_id),  # 현재 원본회의의 후속회의만
                MeetingUser.user_id == user_id,
                MeetingUser.role_id == HOST_ROLE_ID,
                ~exists().where(Calendar.agent_meeting_id == str(meeting_id))  # 현재 회의 ID로 처리되었는지 확인
            )
        )
        
        result = await db.execute(stmt)
        pending_meetings = result.scalars().all()
        
        response_list = []
        for meeting in pending_meetings:
            response_list.append(PendingMeetingResponse(
                meeting_id=meeting.meeting_id,
                meeting_title=meeting.meeting_title,
                meeting_date=meeting.meeting_date,
                meeting_agenda=meeting.meeting_agenda,
                project_id=meeting.project_id
            ))
        return response_list
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"잘못된 UUID 형식: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")

@router.post(
    "/{meeting_id}/accept",
    response_model=MeetingActionResponse,
    summary="예정 회의 수락",
    description="PO 권한을 확인한 뒤 예정 회의를 캘린더에 등록하고 필요 시 회의 정보를 수정합니다.",
)
async def accept_meeting(
    request: Request,
    meeting_id: UUID,
    accept_request: AcceptMeetingRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: TokenPayload = Depends(check_access_token)
):
    """
    2️⃣ 예정 회의 캘린더 등록 API
    
    PO 권한 체크 후 calendar 테이블에 INSERT
    """
    try:
        user_id = UUID(current_user.id)
        agent_meeting_id = accept_request.agent_meeting_id
        
        # Agent 회의 정보 조회
        stmt = select(Meeting).where(Meeting.meeting_id == agent_meeting_id)
        result = await db.execute(stmt)
        agent_meeting = result.scalar_one_or_none()
        
        if not agent_meeting:
            raise HTTPException(status_code=404, detail="예정 회의를 찾을 수 없습니다.")
        
        # PO 권한 체크 (원본 회의 ID로 체크)
        is_po = await check_po_permission(db, user_id, meeting_id)
        if not is_po:
            raise HTTPException(status_code=403, detail="PO 권한이 필요합니다.")
        
        # 이미 처리된 회의인지 확인 (원본 회의 ID로 확인)
        existing_calendar_stmt = select(Calendar).where(
            Calendar.agent_meeting_id == str(meeting_id)
        )
        existing_result = await db.execute(existing_calendar_stmt)
        if existing_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="이미 처리된 예정 회의입니다.")
        
        # Calendar 테이블에 INSERT
        # timezone 정보 제거 (데이터베이스가 TIMESTAMP WITHOUT TIME ZONE 사용)
        meeting_start = accept_request.meeting_date or agent_meeting.meeting_date
        if meeting_start.tzinfo is not None:
            meeting_start = meeting_start.replace(tzinfo=None)
            
        calendar_entry = await insert_meeting_calendar(
            db=db,
            user_id=user_id,
            project_id=agent_meeting.project_id,
            title=accept_request.meeting_title or agent_meeting.meeting_title,
            start=meeting_start,
            meeting_id=agent_meeting.meeting_id,  # meeting_id 명시적으로 전달
            calendar_type="meeting",
            completed=False,
            created_at=datetime.datetime.now(),
            status="active"
        )
        
        # ✅ 후속회의(agent_meeting_id) 업데이트
        followup_meeting_stmt = select(Meeting).where(Meeting.meeting_id == agent_meeting_id)
        followup_result = await db.execute(followup_meeting_stmt)
        followup_meeting = followup_result.scalar_one_or_none()
        
        if followup_meeting:
            # 사용자가 입력한 값으로 후속회의 정보 업데이트
            if accept_request.meeting_title:
                followup_meeting.meeting_title = accept_request.meeting_title
            if accept_request.meeting_date:
                # timezone 정보 제거
                update_date = accept_request.meeting_date
                if update_date.tzinfo is not None:
                    update_date = update_date.replace(tzinfo=None)
                followup_meeting.meeting_date = update_date
            if accept_request.meeting_agenda:
                followup_meeting.meeting_agenda = accept_request.meeting_agenda
            
            await db.commit()
            print(f"[accept_meeting] 후속회의 업데이트 완료: {agent_meeting_id}", flush=True)
        else:
            print(f"[accept_meeting] 후속회의를 찾을 수 없음: {agent_meeting_id}", flush=True)
        
        return {
            "success": True,
            "message": "예정 회의가 캘린더에 등록되었습니다.",
            "calendar_id": calendar_entry.calendar_id
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"잘못된 UUID 형식: {str(e)}")
    except Exception as e:
        await db.rollback()
        print(f"[accept_meeting] 오류 발생: {str(e)}", flush=True)
        print(f"[accept_meeting] 오류 타입: {type(e)}", flush=True)
        import traceback
        print(f"[accept_meeting] 스택 트레이스: {traceback.format_exc()}", flush=True)
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")

@router.post(
    "/{meeting_id}/reject",
    response_model=MeetingActionResponse,
    summary="예정 회의 거부",
    description="PO 권한을 확인한 뒤 예정 회의를 거부 처리하고 캘린더에 거부 상태로 기록합니다.",
)
async def reject_meeting(
    request: Request,
    meeting_id: UUID,
    reject_request: RejectMeetingRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: TokenPayload = Depends(check_access_token)
):
    """
    3️⃣ 예정 회의 거부 처리 API
    
    PO 권한 체크 후 calendar 테이블에 거부 기록 INSERT
    """
    try:
        user_id = UUID(current_user.id)
        agent_meeting_id = reject_request.agent_meeting_id
        
        # Agent 회의 정보 조회
        stmt = select(Meeting).where(Meeting.meeting_id == agent_meeting_id)
        result = await db.execute(stmt)
        agent_meeting = result.scalar_one_or_none()
        
        if not agent_meeting:
            raise HTTPException(status_code=404, detail="예정 회의를 찾을 수 없습니다.")
        
        # PO 권한 체크 (원본 회의 ID로 체크)
        is_po = await check_po_permission(db, user_id, meeting_id)
        if not is_po:
            raise HTTPException(status_code=403, detail="PO 권한이 필요합니다.")
        
        # 이미 처리된 회의인지 확인 (원본 회의 ID로 확인)
        existing_calendar_stmt = select(Calendar).where(
            Calendar.agent_meeting_id == str(meeting_id)
        )
        existing_result = await db.execute(existing_calendar_stmt)
        if existing_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="이미 처리된 예정 회의입니다.")
        
        # Calendar 테이블에 거부 기록 INSERT
        # timezone 정보 제거 (데이터베이스가 TIMESTAMP WITHOUT TIME ZONE 사용)
        meeting_start = agent_meeting.meeting_date
        if meeting_start.tzinfo is not None:
            meeting_start = meeting_start.replace(tzinfo=None)
            
        calendar_entry = await insert_meeting_calendar(
            db=db,
            user_id=user_id,
            project_id=agent_meeting.project_id,
            title=f"[거부됨] {agent_meeting.meeting_title}",
            start=meeting_start,
            meeting_id=agent_meeting.meeting_id,  # meeting_id 명시적으로 전달
            calendar_type="meeting",
            completed=False,
            created_at=datetime.datetime.now(),
            status="rejected"
        )
        
        # ✅ 후속회의(agent_meeting_id) 제목 업데이트 (삭제 대신)
        agent_meeting.meeting_title = f"[거부됨] {agent_meeting.meeting_title}"
        await db.commit()
        print(f"[reject_meeting] 후속회의 제목 업데이트 완료: {agent_meeting_id}", flush=True)
        print(f"[reject_meeting] 업데이트된 제목: {agent_meeting.meeting_title}", flush=True)
        
        return {
            "success": True,
            "message": "예정 회의가 거부되었습니다.",
            "calendar_id": calendar_entry.calendar_id
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"잘못된 UUID 형식: {str(e)}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")

@router.get(
    "/prompt-logs/{meeting_id}",
    response_model=MeetingPromptLogsByMeetingResponse,
    summary="특정 회의 프롬프트 로그 조회",
    description="회의 ID 기준으로 에이전트 프롬프트 로그를 조회하며, 필요 시 에이전트 타입으로 필터링합니다.",
)
async def get_meeting_prompt_logs(
    meeting_id: str,
    agent_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session)
):
    """
    특정 회의의 프롬프트 로그 조회
    
    Args:
        meeting_id: 회의 ID
        agent_type: 에이전트 타입 필터 ('search', 'summary', 'docs')
    """
    try:
        logs = await get_prompt_logs_by_meeting(db, meeting_id, agent_type)
        return {
            "meeting_id": meeting_id,
            "agent_type": agent_type,
            "logs": logs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"프롬프트 로그 조회 중 오류: {str(e)}")

@router.get(
    "/prompt-logs",
    response_model=MeetingPromptLogsResponse,
    summary="전체 회의 프롬프트 로그 조회",
    description="전체 회의의 프롬프트 로그를 조회하며, 필요 시 에이전트 타입으로 필터링합니다.",
)
async def get_all_meeting_prompt_logs(
    agent_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session)
):
    """
    모든 회의의 프롬프트 로그 조회
    
    Args:
        agent_type: 에이전트 타입 필터 ('search', 'summary', 'docs')
    """
    try:
        logs = await get_all_prompt_logs(db, agent_type)
        return {
            "agent_type": agent_type,
            "total_count": len(logs),
            "logs": logs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"프롬프트 로그 조회 중 오류: {str(e)}") 