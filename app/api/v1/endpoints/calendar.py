from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.db_session import get_db_session
from app.services.calendar_service.calendar_crud import get_calendars_by_user_and_project_filtered, update_calendar, update_calendar_by_meeting_id
from app.schemas.calendar import CalendarResponse
from typing import List
from uuid import UUID

router = APIRouter()

@router.get("/{user_id}/{project_id}", summary="사용자의 프로젝트별 캘린더 조회", response_model=List[CalendarResponse])
async def read_calendars_by_user_and_project(user_id: UUID, project_id: UUID, db: AsyncSession = Depends(get_db_session)):
    """사용자의 프로젝트별 캘린더를 조회합니다."""
    calendars = await get_calendars_by_user_and_project_filtered(user_id, project_id, db)
    return calendars

@router.put("/{calendar_id}", summary="캘린더 수정", response_model=CalendarResponse)
async def edit_calendar(calendar_id: UUID, body: dict, db: AsyncSession = Depends(get_db_session)):
    """ 캘린더 수정을 합니다. """
    calendar = await update_calendar(
        calendar_id=calendar_id,
        completed=body["completed"],
        db=db
    )
    if not calendar:
        raise HTTPException(status_code=404, detail="Calendar not found")
    return calendar

@router.put("/by-meeting/{meeting_id}", summary="meeting_id로 캘린더 수정", response_model=CalendarResponse)
async def edit_calendar_by_meeting_id(meeting_id: UUID, body: dict, db: AsyncSession = Depends(get_db_session)):
    """ meeting_id로 캘린더 수정을 합니다. """
    calendar = await update_calendar_by_meeting_id(
        meeting_id=meeting_id,
        completed=body["completed"],
        db=db
    )
    if not calendar:
        raise HTTPException(status_code=404, detail="Calendar not found")
    return calendar 