from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends, Body, BackgroundTasks
from fastapi import APIRouter
from app.services.stt import stt_from_file
from app.services.tagging import tag_chunks_async, save_prompt_log
from app.services.docs_service.orchestration import super_agent_for_meeting
import json
import os
import re
import aiofiles
from typing import List, Optional, Dict, Tuple
from pydantic import BaseModel, UUID4
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.db_session import get_db_session
from app.crud.crud_meeting import insert_meeting, insert_meeting_user, get_project_meetings, insert_prompt_log, update_meeting_user, update_meeting
from app.models.project_user import ProjectUser
from app.models.flowy_user import FlowyUser
from app.models.role import Role
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.meeting import Meeting
from app.services.calendar_service.calendar_crud import insert_meeting_calendar, update_calendar_by_meeting_id
from app.services.notify_email_service import send_meeting_update_email, send_meeting_email_without_update
from fastapi.responses import JSONResponse
import mutagen
from app.models.calendar import Calendar
from app.models.meeting_user import MeetingUser
from app.schemas.stt_schema import STTResponse, ProjectUsersResponse, MessageResponse

router = APIRouter()

class Attendee(BaseModel):
    name: str
    email: str
    role: str

def parse_attendees(
    attendees: List[str] = Form(...)
):
    attendees_list = []
    for attendee_json in attendees:
        try:
            attendee = json.loads(attendee_json)
            if not all(k in attendee for k in ("name", "email", "role")):
                raise ValueError
            attendees_list.append(attendee)
        except Exception:
            raise HTTPException(status_code=400, detail="attendees 형식 오류 (name, email, role 필수, JSON 문자열로 입력)")
    return attendees_list

async def run_stt_in_background(
    temp_path: str,
    project_id: str,
    meeting_id: str,
    meeting_title: str,
    meeting_agenda: str,
    meeting_date: str,
    host_id: str,
    host_name: str,
    host_email: str,
    host_role: str,
    attendees_ids: list,
    attendees_name: list,
    attendees_email: list,
    attendees_role: list,
    subject: str,
    db: AsyncSession
):
    import os
    import aiofiles
    from datetime import datetime
    from app.services.tagging import tag_chunks_async
    from app.services.docs_service.docs_recommend import recommend_documents
    from app.crud.crud_meeting import insert_meeting, insert_meeting_user
    from app.models.flowy_user import FlowyUser
    from app.services.calendar_service.calendar_crud import insert_meeting_calendar
    from app.services.stt import stt_from_file

    try:
        def split_items(items):
            result = []
            for item in items:
                result.extend([i.strip() for i in item.split(",") if i.strip()])
            return result
        ids = split_items(attendees_ids)
        names = split_items(attendees_name)
        emails = split_items(attendees_email)
        roles = split_items(attendees_role)
        attendees_list = [
            {
                "id": host_id,
                "name": host_name,
                "email": host_email,
                "role": host_role,
                "is_host": True
            }
        ] + [
            {
                "id": i,
                "name": n,
                "email": e,
                "role": r,
                "is_host": False
            }
            for i, n, e, r in zip(ids, names, emails, roles)
        ]
        def get_audio_duration_minutes(file_path):
            try:
                import mutagen
                audio = mutagen.File(file_path)
                if audio is None or not hasattr(audio, 'info') or not hasattr(audio.info, 'length'):
                    return 0
                return round(audio.info.length / 60, 2)
            except Exception as e:
                print(f"[stt_api] audio duration error: {e}", flush=True)
                return 0
        duration_minutes = get_audio_duration_minutes(temp_path)
        meeting_date_obj = datetime.strptime(meeting_date, "%Y-%m-%d %H:%M:%S")
        HOST_ROLE_ID = "20ea65e2-d3b7-4adb-a8ce-9e67a2f21999"
        ATTENDEE_ROLE_ID = "a55afc22-b4c1-48a4-9513-c66ff6ed3965"
        # meeting_id를 항상 str로 변환해서 체크
        if not meeting_id or str(meeting_id).strip() == '':
            # meeting insert
            meeting = await insert_meeting(
                db=db,
                project_id=project_id,
                meeting_title=meeting_title,
                meeting_agenda=meeting_agenda,
                meeting_date=meeting_date_obj,
                meeting_audio_path=temp_path
            )
            meeting_id = meeting.meeting_id
        else:
            # meeting update
            existing_meeting = await db.execute(
                select(Meeting).where(Meeting.meeting_id == meeting_id)
            )
            meeting_obj = existing_meeting.scalar_one_or_none()
            if meeting_obj:
                await update_meeting(
                    db=db,
                    meeting_id=meeting_id,
                    meeting_title=meeting_title,
                    meeting_agenda=meeting_agenda,
                    meeting_date=meeting_date_obj,
                    meeting_audio_path=temp_path
                )
                meeting = meeting_obj
            else:
                meeting = await insert_meeting(
                    db=db,
                    project_id=project_id,
                    meeting_title=meeting_title,
                    meeting_agenda=meeting_agenda,
                    meeting_date=meeting_date_obj,
                    meeting_audio_path=temp_path
                )
                meeting_id = meeting.meeting_id
        all_ids = [host_id] + list(ids)
        all_names = [host_name] + list(names)
        all_emails = [host_email] + list(emails)
        all_roles = [HOST_ROLE_ID] + [ATTENDEE_ROLE_ID] * len(names)
        for id, name, email, role_id in zip(all_ids, all_names, all_emails, all_roles):
            user = await db.execute(
                select(FlowyUser).where(FlowyUser.user_id == id)
            )
            user_obj = user.scalar_one_or_none()
            if not user_obj:
                continue
            # meeting_user도 update/insert 분기
            if not meeting_id or str(meeting_id).strip() == '':
                # meeting_id가 빈 값이면 insert만 실행
                await insert_meeting_user(
                    db=db,
                    meeting_id=meeting.meeting_id,
                    user_id=user_obj.user_id,
                    role_id=role_id
                )
            else:
                # meeting_id가 있으면 update/insert 분기
                existing_meeting_user = await db.execute(
                    select(MeetingUser).where(
                        MeetingUser.meeting_id == meeting.meeting_id,
                        MeetingUser.user_id == user_obj.user_id
                    )
                )
                meeting_user_obj = existing_meeting_user.scalar_one_or_none()
                if meeting_user_obj:
                    await update_meeting_user(
                        db=db,
                        meeting_user_id=meeting_user_obj.meeting_user_id,
                        role_id=role_id
                    )
                else:
                    await insert_meeting_user(
                        db=db,
                        meeting_id=meeting.meeting_id,
                        user_id=user_obj.user_id,
                        role_id=role_id
                    )
            # calendar도 update/insert 분기
            if not meeting_id or str(meeting_id).strip() == '':
                # insert
                await insert_meeting_calendar(
                    db=db,
                    user_id=user_obj.user_id,
                    project_id=meeting.project_id,
                    title=meeting_title,
                    start=meeting_date_obj,
                    meeting_id=meeting.meeting_id,
                )
            else:
                # update
                calendar = await db.execute(
                    select(Calendar).where(Calendar.meeting_id == meeting_id)
                )
                calendar_obj = calendar.scalars().all()
                if calendar_obj:
                    await update_calendar_by_meeting_id(
                        meeting_id=meeting_id,
                        user_id=user_obj.user_id,
                        title=meeting_title,
                        start=meeting_date_obj,
                        updated_at=datetime.now(),
                        db=db
                    )
                else:
                    await insert_meeting_calendar(
                        db=db,
                        user_id=user_obj.user_id,
                        project_id=meeting.project_id,
                        title=meeting_title,
                        start=meeting_date_obj,
                        meeting_id=meeting_id,
                    )
        stt_result = await stt_from_file(temp_path)
        chunks = stt_result.get("chunks")
        if not chunks:
            print("[BackgroundTask] stt 변환 결과 없음", flush=True)
            return
        tag_result = await tag_chunks_async(
            project_name=project_id,
            subject=subject,
            chunks=chunks,
            attendees_list=attendees_list,
            agenda=meeting_agenda,
            meeting_date=meeting_date,
            db=db,
            meeting_id=meeting.meeting_id,
            meeting_duration_minutes=duration_minutes
        )
        all_txt_result = " ".join(tag_result.get("all_sentences") or [])
        
        # ========== Docs/Search Agent 시작/완료 시간 추적 ==========
        docs_search_start_time = datetime.now()
        print(f"[BackgroundTask] Docs/Search Agent 시작: {docs_search_start_time}", flush=True)
        
        # 내부문서/외부문서 프롬프트 로그 (orchestration.py에서 내부적으로 docs와 search 분리 저장)
        search_result = await super_agent_for_meeting(all_txt_result, db=db, meeting_id=meeting.meeting_id)
        
        docs_search_end_time = datetime.now()
        print(f"[BackgroundTask] Docs/Search Agent 완료: {docs_search_end_time} (소요시간: {docs_search_end_time - docs_search_start_time})", flush=True)
        
        urls = re.findall(r'https?://\S+', search_result)
        print(f"\n\n[BackgroundTask] 찾은 문서 링크 :\n {search_result}\n\n", flush=True)
        
        doc_recommend_result = await recommend_documents(subject)
        print(f"[BackgroundTask] 분석 완료: meeting_id={meeting.meeting_id}", flush=True)
    except Exception as e:
        print(f"[BackgroundTask] 전체 분석 작업 중 오류: {e}", flush=True)
    finally:
        try:
            os.remove(temp_path)
            print(f"[BackgroundTask] 임시 파일 삭제 완료: {temp_path}", flush=True)
        except Exception as e:
            print(f"[BackgroundTask] 파일 삭제 오류: {e}", flush=True)

@router.post(
    "/",
    response_model=STTResponse,
    summary="회의 음성 파일 STT 변환 및 분석",
    description="""
    음성 파일을 업로드하면 백그라운드에서 STT 변환 및 회의 분석을 수행합니다.
    
    - Whisper API로 음성 → 텍스트 변환
    - GPT로 텍스트 후처리
    - 요약 / 피드백 / 할 일 추출 / 예정 회의 등록
    - 지원 형식: flac, m4a, mp3, mp4, mpeg, mpga, oga, ogg, wav, webm
    """
)
async def stt_api(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="지원 형식: flac, m4a, mp3, mp4, mpeg, mpga, oga, ogg, wav, webm"),
    project_id: str = Form(..., description="프로젝트 ID"),
    meeting_id: str = Form(..., description="회의 ID (신규 생성 시 빈 문자열)"),
    meeting_title: str = Form(..., description="회의 제목"),
    meeting_agenda: str = Form(..., description="회의 안건"),
    meeting_date: str = Form(..., description="회의 날짜 (형식: YYYY-MM-DD HH:MM:SS)"),
    host_id: str = Form(..., description="회의장 사용자 ID"),
    host_name: str = Form(..., description="회의장 이름"),
    host_email: str = Form(..., description="회의장 이메일"),
    host_role: str = Form(..., description="회의장 역할"),
    attendees_ids: List[str] = Form(..., description="참석자 ID 목록 (쉼표 구분 가능)"),
    attendees_name: List[str] = Form(..., description="참석자 이름 목록"),
    attendees_email: List[str] = Form(..., description="참석자 이메일 목록"),
    attendees_role: List[str] = Form(..., description="참석자 역할 목록"),
    subject: str = Form(..., description="회의 주제"),
    db: AsyncSession = Depends(get_db_session)
):
    print("[stt_api] ====== 입력 파라미터 디버깅 ======")
    print(f"file.filename: {file.filename}")
    print(f"project_id: {project_id}")
    print(f"meeting_id: {meeting_id}")
    print(f"meeting_title: {meeting_title}")
    print(f"meeting_agenda: {meeting_agenda}")
    print(f"meeting_date: {meeting_date}")
    print(f"host_id: {host_id}")
    print(f"host_name: {host_name}")
    print(f"host_email: {host_email}")
    print(f"host_role: {host_role}")
    print(f"attendees_ids: {attendees_ids}")
    print(f"attendees_name: {attendees_name}")
    print(f"attendees_email: {attendees_email}")
    print(f"attendees_role: {attendees_role}")
    print(f"subject: {subject}")
    print("[stt_api] ==================================")
    
    # 지원되는 오디오 형식 확인
    SUPPORTED_AUDIO_FORMATS = {
        'flac', 'm4a', 'mp3', 'mp4', 'mpeg', 'mpga', 'oga', 'ogg', 'wav', 'webm'
    }
    
    if file.filename:
        file_extension = file.filename.lower().split('.')[-1]
        if file_extension not in SUPPORTED_AUDIO_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"지원되지 않는 파일 형식입니다. 지원 형식: {', '.join(sorted(SUPPORTED_AUDIO_FORMATS))}"
            )
    
    import aiofiles
    temp_path = f"temp_{file.filename}"
    async with aiofiles.open(temp_path, "wb") as f:
        content = await file.read()
        await f.write(content)
    background_tasks.add_task(
        run_stt_in_background,
        temp_path,
        project_id,
        meeting_id,
        meeting_title,
        meeting_agenda,
        meeting_date,
        host_id,
        host_name,
        host_email,
        host_role,
        attendees_ids,
        attendees_name,
        attendees_email,
        attendees_role,
        subject,
        db
    )
    return {"message": "분석 작업이 백그라운드에서 시작되었습니다."}

@router.get(
    "/project-users/{project_id}",
    response_model=ProjectUsersResponse,
    summary="프로젝트 참석자 목록 조회",
    description="프로젝트 ID로 해당 프로젝트의 참석자 목록을 조회합니다."
)
async def get_project_users(
    project_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    # 비동기 쿼리 실행
    stmt = select(ProjectUser).where(ProjectUser.project_id == project_id)
    result = await db.execute(stmt)
    project_users = result.scalars().all()
    
    print("=== Project Users Query Result ===")
    print(f"Project ID: {project_id}")
    print(f"Number of users found: {len(project_users)}")
    
    users = []
    for pu in project_users:
        # 비동기 쿼리 실행
        stmt = select(FlowyUser).where(FlowyUser.user_id == pu.user_id)
        result = await db.execute(stmt)
        flowy_user = result.scalar_one_or_none()
        
        if flowy_user:
            print(f"\nUser ID: {pu.user_id}")
            print(f"Role ID: {pu.role_id}")
            print(f"Name: {flowy_user.user_name}")
            print(f"Email: {flowy_user.user_email}")
            users.append({
                "user_id": pu.user_id,
                "role_id": pu.role_id,
                "name": flowy_user.user_name,
                "email": flowy_user.user_email,
                "user_jobname": flowy_user.user_jobname
            })
    
    return {"users": users}

@router.post(
    "/meeting/send-update-email",
    response_model=MessageResponse,
    summary="회의 업데이트 이메일 발송",
    description="회의 정보가 변경되었을 때 참석자들에게 업데이트 이메일을 발송합니다."
)
async def send_update_email_api(data: dict = Body(...)):
    # info_n, dt, subj, update_dt, meeting_id 등 프론트에서 넘긴 값 사용
    await send_meeting_update_email(data)
    return {"message": "메일 전송 완료"}

@router.post(
    "/meeting/send-meeting-result",
    response_model=MessageResponse,
    summary="회의 결과 이메일 발송",
    description="회의 분석 결과를 참석자들에게 이메일로 발송합니다."
)
async def send_meeting_result(meeting_info: dict):
    await send_meeting_email_without_update(meeting_info)
    return JSONResponse(content={"message": "메일 전송 완료"})


