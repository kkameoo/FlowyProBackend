from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.db_session import get_db_session
from app.crud.crud_user import get_all_users
from app.schemas.signup_info import TokenPayload
from app.schemas.project import ProjectCreate, ProjectNameUpdate, TaskAssignLogCreate, SummaryLogCreate, ProjectUpdateRequestBody, SummaryAndTaskRequest, MeetingCreateRequest
from app.schemas.project_response import (
    GenericListResponse,
    GenericObjectResponse,
    MeetingCreateResponse,
    MessageResponse,
    ProjectCreateResponse,
    ProjectMetaResponse,
)
from app.services.signup_service.auth import check_access_token
from app.crud.crud_project import get_project_users_with_projects_by_user_id, get_meetings_with_users_by_project_id, create_project, get_meeting_detail_with_project_and_users, update_project_name_by_id, insert_task_assign_log, insert_summary_log, update_project_with_users, insert_summary_and_task_logs
from uuid import UUID
import traceback
from fastapi.responses import JSONResponse
from app.services.calendar_service.calendar_crud import update_calendar_from_todos, insert_meeting_calendar
from app.crud.crud_meeting import insert_meeting, insert_meeting_user, get_role_id_by_user_and_project
from app.models.flowy_user import FlowyUser
from datetime import datetime
from typing import Any

router = APIRouter()


@router.post(
    "",
    response_model=ProjectCreateResponse,
    summary="프로젝트 생성",
    description="프로젝트 기본 정보와 참여 사용자 목록을 받아 새 프로젝트를 생성합니다.",
)
async def create_project_api(
    project_data: ProjectCreate,
    db: AsyncSession = Depends(get_db_session)
):
    try:
        result = await create_project(project_data, db)
        return result
    except Exception as e:
    # 전체 traceback 문자열로 출력
        traceback_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        print("🔥 서버 에러:", traceback_str)  # 콘솔에 출력

        return JSONResponse(
            status_code=500,
            content={"detail": str(e), "traceback": traceback_str}
        )


@router.get(
    "/meta",
    response_model=ProjectMetaResponse,
    summary="프로젝트 생성 메타 조회",
    description="현재 사용자 기준으로 같은 회사의 사용자 목록과 역할 목록을 조회합니다.",
)
async def list_users(token_user = Depends(check_access_token), db: AsyncSession = Depends(get_db_session)):
    users = await get_all_users(token_user, db)
    return users

@router.get(
    "/user_id/{user_id}",
    response_model=GenericListResponse,
    summary="사용자 프로젝트 목록 조회",
    description="사용자 ID로 참여 중인 프로젝트 목록과 프로젝트별 참여자 수를 조회합니다.",
)
async def read_user_projects(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    projects = await get_project_users_with_projects_by_user_id(db, user_id)
    return {"data": projects}

@router.get(
    "/meeting/{project_id}",
    response_model=GenericListResponse,
    summary="프로젝트 회의 목록 조회",
    description="프로젝트의 회의 목록과 분석 상태를 최신 순으로 조회합니다.",
)
async def read_meetings_with_users(project_id: UUID, db: AsyncSession = Depends(get_db_session)):
    meetings = await get_meetings_with_users_by_project_id(db, project_id)
    return {"data": meetings}

@router.get(
    "/meeting/result/{meeting_id}",
    response_model=GenericObjectResponse,
    summary="회의 분석 결과 상세 조회",
    description="회의 기본 정보, 프로젝트 정보, 참여자, 최신 요약/피드백/역할 분배 로그를 조회합니다.",
)
async def meetings_with_result(meeting_id: UUID ,db: AsyncSession = Depends(get_db_session)):
    meetings = await get_meeting_detail_with_project_and_users(db, meeting_id)
    return {"data": meetings}

# @router.delete("/{project_id}")
# async def delete_project(project_id: UUID, db: AsyncSession = Depends(get_db_session)):
#     deleted = await delete_project_by_id(db, project_id)
#     if not deleted:
#         raise HTTPException(status_code=404, detail="Project not found")
#     return {"message": "Project deleted successfully"}

@router.put(
    "/{project_id}",
    response_model=MessageResponse,
    summary="프로젝트 이름 수정",
    description="프로젝트 ID로 프로젝트 이름을 수정합니다.",
)
async def update_project_name(
    project_id: UUID,
    data: ProjectNameUpdate,
    db: AsyncSession = Depends(get_db_session)
):
    updated = await update_project_name_by_id(db, project_id, data.project_name)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project name updated successfully"}

@router.post(
    "/update_todos",
    response_model=MessageResponse,
    summary="회의 할 일 로그 저장",
    description="회의의 역할 분배/할 일 업데이트 로그를 저장합니다.",
)
async def create_task_assign_log(
    log_data: TaskAssignLogCreate,
    db: AsyncSession = Depends(get_db_session)
):
    success = await insert_task_assign_log(
        db=db,
        meeting_id=log_data.meeting_id,
        updated_task_assign_contents=log_data.updated_task_assign_contents
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create task assign log")
    return {"message": "Task assign log created successfully"}

@router.post(
    "/update_summary",
    response_model=MessageResponse,
    summary="회의 요약 로그 저장",
    description="회의 요약 업데이트 로그를 저장합니다.",
)
async def create_summary_log(
    log_data: SummaryLogCreate,
    db: AsyncSession = Depends(get_db_session)
):
    success = await insert_summary_log(
        db=db,
        meeting_id=log_data.meeting_id,
        updated_summary_contents=log_data.updated_summary_contents
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create task assign log")
    return {"message": "Task assign log created successfully"}

@router.post(
    "/update_summary_task",
    response_model=MessageResponse,
    summary="요약/할 일 동시 저장",
    description="회의 요약과 할 일 로그를 동시에 저장하고 할 일 기반 캘린더를 갱신합니다.",
)
async def create_summary_and_task(
    data: SummaryAndTaskRequest,  # pydantic 모델
    db: AsyncSession = Depends(get_db_session)
):
    success = await insert_summary_and_task_logs(
        db,
        meeting_id=data.meeting_id,
        updated_summary_contents=data.updated_summary_contents,
        updated_task_assign_contents=data.updated_task_assign_contents
    )
    
    calendar_result = await update_calendar_from_todos(
        db=db,
        meeting_id=data.meeting_id,
        updated_task_assign_contents=data.updated_task_assign_contents
    )

    if not success:
        raise HTTPException(status_code=500, detail="저장 실패")
    return {"message": "저장 완료"}



@router.put(
    "/update_project_with_users/{project_id}",
    response_model=MessageResponse,
    summary="프로젝트 정보/참여자 수정",
    description="프로젝트 이름/설명과 참여자 목록(역할 포함)을 함께 수정합니다.",
)
async def update_project(
    project_id: UUID,
    body: ProjectUpdateRequestBody,
    db: AsyncSession = Depends(get_db_session),
):
    success = await update_project_with_users(
        db=db,
        project_id=project_id,
        project_name=body.project_name,
        project_detail=body.project_detail,
        new_users=body.project_users,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project updated"}

@router.post(
    "/meeting/create",
    response_model=MeetingCreateResponse,
    summary="회의 생성",
    description="프로젝트 회의를 생성하고 회의 참여자와 사용자 캘린더 일정을 함께 등록합니다.",
)
async def create_meeting_with_users(
    meeting_data: MeetingCreateRequest,
    db: AsyncSession = Depends(get_db_session)
):
    try:
        meeting_date_obj = datetime.fromisoformat(meeting_data.meeting_date)

        # 👉 timezone-aware일 경우, tz를 제거하여 naive datetime으로 변환
        if meeting_date_obj.tzinfo is not None:
            meeting_date_obj = meeting_date_obj.replace(tzinfo=None)

        meeting = await insert_meeting(
            db=db,
            project_id=meeting_data.project_id,
            meeting_title=meeting_data.meeting_title,
            meeting_agenda=meeting_data.meeting_agenda,
            meeting_date=meeting_date_obj,
            meeting_audio_path=meeting_data.meeting_audio_path
        )
        for user in meeting_data.users:
            await insert_meeting_user(
                db=db,
                meeting_id=meeting.meeting_id,
                user_id=user.user_id,
                role_id=user.role_id
            )
            await insert_meeting_calendar(
                db=db,
                user_id=user.user_id,
                project_id=meeting_data.project_id,
                title=meeting_data.meeting_title,
                start=meeting_date_obj,
                meeting_id=meeting.meeting_id
            )
        return {"meeting_id": meeting.meeting_id}
    except Exception as e:
        traceback_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        print("🔥 서버 에러:", traceback_str)
        return JSONResponse(
            status_code=500,
            content={"detail": str(e), "traceback": traceback_str}
        )
