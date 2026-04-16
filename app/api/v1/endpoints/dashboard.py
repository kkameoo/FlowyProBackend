from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import List, Optional
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, and_, or_, select, text
from sqlalchemy.orm import selectinload

from app.db.db_session import get_db_session
from app.models.meeting import Meeting
from app.models.feedback import Feedback
from app.models.feedbacktype import FeedbackType
from app.models.project import Project
from app.models.flowy_user import FlowyUser
from app.models.meeting_user import MeetingUser
from app.services.admin_service.admin_check import get_current_user
from .dashboard_repo import get_summary_data, get_chart_data, get_table_data

router = APIRouter()

# Pydantic 모델을 schemas에서 import
from app.schemas.dashboard import DashboardResponse, DashboardSummary, ChartData, TableData, DashboardFilterOptionsResponse

@router.get("/stats", summary="대시보드 통계 데이터 조회", response_model=DashboardResponse)
async def get_dashboard_stats(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user = Depends(get_current_user),
    period: str = Query("month", description="기간 타입: year, quarter, month, week, day"),
    project_id: Optional[str] = Query(None, description="프로젝트 ID"),
    department: Optional[str] = Query(None, description="부서명"),
    user_id: Optional[str] = Query(None, description="사용자 ID"),
    start_date: Optional[str] = Query(None, description="시작 날짜 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="종료 날짜 (YYYY-MM-DD)")
):
    """
    대시보드 통계 데이터를 조회합니다.
    """
    try:
        # 현재 로그인한 사용자의 실제 정보를 DB에서 조회
        user_query = select(FlowyUser).where(FlowyUser.user_login_id == current_user.login_id)
        user_result = await db.execute(user_query)
        current_user_info = user_result.scalar_one_or_none()
        
        if not current_user_info:
            raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다.")
        
        # 날짜 문자열을 datetime으로 변환
        parsed_start_date = None
        parsed_end_date = None
        
        if start_date:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="시작 날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식으로 입력해주세요.")
        
        if end_date:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="종료 날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식으로 입력해주세요.")
        
        # 기본 날짜 범위 설정
        if not parsed_start_date:
            parsed_start_date = datetime.now() - timedelta(days=365)
        if not parsed_end_date:
            parsed_end_date = datetime.now()

        # 필터 조건 구성
        filters = []
        
        if project_id:
            try:
                project_uuid = UUID(project_id)
                filters.append(Meeting.project_id == project_uuid)
            except ValueError:
                raise HTTPException(status_code=400, detail="프로젝트 ID 형식이 올바르지 않습니다.")
        
        # 사용자가 선택되었지만 부서가 선택되지 않은 경우, 해당 사용자의 부서를 자동으로 추가
        auto_department = None
        if user_id and not department:
            try:
                user_uuid = UUID(user_id)
                # 선택된 사용자의 부서 정보 조회
                user_dept_query = select(FlowyUser.user_dept_name).where(
                    FlowyUser.user_id == user_uuid,
                    FlowyUser.user_company_id == current_user_info.user_company_id
                )
                user_dept_result = await db.execute(user_dept_query)
                auto_department = user_dept_result.scalar_one_or_none()
                
                if auto_department:
                    filters.append(FlowyUser.user_dept_name == auto_department)
            except ValueError:
                raise HTTPException(status_code=400, detail="사용자 ID 형식이 올바르지 않습니다.")
        
        # 부서 필터 (사용자가 직접 선택한 경우 또는 자동 추가된 경우)
        if department:
            filters.append(FlowyUser.user_dept_name == department)
        
        if user_id:
            try:
                user_uuid = UUID(user_id)
                filters.append(FlowyUser.user_id == user_uuid)
            except ValueError:
                raise HTTPException(status_code=400, detail="사용자 ID 형식이 올바르지 않습니다.")
        if parsed_start_date and parsed_end_date:
            filters.append(Meeting.meeting_date.between(parsed_start_date, parsed_end_date))
            
        # 회사 필터 추가
        filters.append(FlowyUser.user_company_id == current_user_info.user_company_id)

        # 1. Summary 데이터 조회
        summary_data = await get_summary_data(db, filters, parsed_start_date, parsed_end_date, period)
        
        # 2. 차트 데이터 조회
        chart_data = await get_chart_data(db, filters, parsed_start_date, parsed_end_date, period)
        
        # 3. 테이블 데이터 조회
        table_data = await get_table_data(db, filters, parsed_start_date, parsed_end_date, period)

        return DashboardResponse(
            summary=summary_data,
            chartData=chart_data,
            tableData=table_data,
            auto_department=auto_department
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"대시보드 데이터 조회 중 오류가 발생했습니다: {str(e)}\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)

@router.get("/filter-options", summary="대시보드 필터 옵션 조회", response_model=DashboardFilterOptionsResponse)
async def get_dashboard_filter_options(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user = Depends(get_current_user),
    project_id: Optional[str] = Query(None, description="선택된 프로젝트 ID"),
    department: Optional[str] = Query(None, description="선택된 부서명"),
    user_id: Optional[str] = Query(None, description="선택된 사용자 ID"),
    start_date: Optional[str] = Query(None, description="시작 날짜 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="종료 날짜 (YYYY-MM-DD)")
):
    """
    대시보드 필터 옵션을 조회합니다. (계층적 필터링 지원)
    """
    try:
        # 현재 로그인한 사용자의 실제 정보를 DB에서 조회
        user_query = select(FlowyUser).where(FlowyUser.user_login_id == current_user.login_id)
        user_result = await db.execute(user_query)
        current_user_info = user_result.scalar_one_or_none()
        
        if not current_user_info:
            raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다.")

        # 날짜 문자열을 datetime으로 변환
        parsed_start_date = None
        parsed_end_date = None
        
        if start_date:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="시작 날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식으로 입력해주세요.")
        
        if end_date:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="종료 날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식으로 입력해주세요.")

        # 1. 프로젝트 목록 (해당 기간에 실제 데이터가 있는 프로젝트만)
        projects_query = (
            select(Project.project_id, Project.project_name)
            .distinct()
            .select_from(Project)
            .join(Meeting, Project.project_id == Meeting.project_id)
            .join(MeetingUser, Meeting.meeting_id == MeetingUser.meeting_id)
            .join(FlowyUser, MeetingUser.user_id == FlowyUser.user_id)
            .where(FlowyUser.user_company_id == current_user_info.user_company_id)
        )
        
        # 날짜 범위가 지정된 경우, 해당 기간에 회의가 있는 프로젝트만 필터링
        if parsed_start_date and parsed_end_date:
            projects_query = projects_query.where(Meeting.meeting_date.between(parsed_start_date, parsed_end_date))
        
        projects_query = projects_query.order_by(Project.project_name)
        projects_result = await db.execute(projects_query)
        projects = [{"id": str(p.project_id), "name": p.project_name} for p in projects_result.all()]

        # 2. 부서 목록 (프로젝트 선택 및 날짜 범위에 따라 필터링)
        departments_query = (
            select(FlowyUser.user_dept_name)
            .distinct()
            .select_from(FlowyUser)
            .join(MeetingUser, FlowyUser.user_id == MeetingUser.user_id)
            .join(Meeting, MeetingUser.meeting_id == Meeting.meeting_id)
            .where(
                FlowyUser.user_dept_name.isnot(None),
                FlowyUser.user_company_id == current_user_info.user_company_id
            )
        )
        
        # 날짜 범위 조건 추가 (해당 기간에 회의가 있는 부서만)
        if parsed_start_date and parsed_end_date:
            departments_query = departments_query.where(Meeting.meeting_date.between(parsed_start_date, parsed_end_date))
        
        # 프로젝트가 선택된 경우, 해당 프로젝트에 참여하는 부서만 조회
        if project_id:
            try:
                project_uuid = UUID(project_id)
                departments_query = departments_query.where(Meeting.project_id == project_uuid)
            except ValueError:
                pass  # 잘못된 UUID 형식인 경우 무시
        
        departments_result = await db.execute(departments_query)
        departments = [d.user_dept_name for d in departments_result.all()]

        # 3. 사용자 목록 (프로젝트/부서 선택 및 날짜 범위에 따라 필터링)
        users_query = (
            select(FlowyUser.user_id, FlowyUser.user_name, FlowyUser.user_login_id, FlowyUser.user_dept_name)
            .select_from(FlowyUser)
            .join(MeetingUser, FlowyUser.user_id == MeetingUser.user_id)
            .join(Meeting, MeetingUser.meeting_id == Meeting.meeting_id)
            .where(FlowyUser.user_company_id == current_user_info.user_company_id)
            .distinct()
        )
        
        # 날짜 범위 조건 추가 (해당 기간에 회의에 참여한 사용자만)
        if parsed_start_date and parsed_end_date:
            users_query = users_query.where(Meeting.meeting_date.between(parsed_start_date, parsed_end_date))
        
        # 프로젝트가 선택된 경우
        if project_id:
            try:
                project_uuid = UUID(project_id)
                users_query = users_query.where(Meeting.project_id == project_uuid)
            except ValueError:
                pass
        
        # 부서가 선택된 경우
        if department:
            users_query = users_query.where(FlowyUser.user_dept_name == department)
        
        users_query = users_query.order_by(FlowyUser.user_name)
        users_result = await db.execute(users_query)
        users = [{"id": str(u.user_id), "name": u.user_name, "login_id": u.user_login_id, "department": u.user_dept_name} for u in users_result.all()]

        # 4. 사용자가 선택된 경우의 처리
        selected_user_department = None
        if user_id:
            try:
                # user_id가 전달된 경우, 해당 사용자의 부서 정보만 반환하고
                # 사용자 목록은 필터링하지 않음 (프론트엔드에서 이미 선택된 사용자가 있으므로)
                user_uuid = UUID(user_id)
                selected_user_query = select(FlowyUser.user_dept_name).where(
                    FlowyUser.user_id == user_uuid,
                    FlowyUser.user_company_id == current_user_info.user_company_id
                )
                selected_user_result = await db.execute(selected_user_query)
                selected_user_department = selected_user_result.scalar_one_or_none()
            except ValueError:
                pass

        return {
            "projects": projects,
            "departments": departments,
            "users": users,
            "selected_user_department": selected_user_department
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"필터 옵션 조회 중 오류가 발생했습니다: {str(e)}") 