from fastapi import APIRouter, status, Depends, HTTPException
from typing import List
from uuid import UUID
from pydantic import BaseModel, EmailStr
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.db_session import get_db_session

from app.services.admin_service.user_crud import UserCRUD
from app.services.admin_service.company_crud import CompanyCRUD
from app.services.admin_service.position_crud import PositionCRUD
from app.services.admin_service.admin_check import require_company_admin, require_super_admin, require_any_admin
from app.services.notify_email_service import send_user_status_change_email

from app.schemas.admin_response import UserByCompanyResponse

# 사용자 관련 Pydantic 모델
class UserBase(BaseModel):
    user_name: str
    user_email: EmailStr
    user_login_id: str
    user_phonenum: str
    user_company_id: UUID
    user_dept_name: str | None = None
    user_team_name: str | None = None
    user_position_id: UUID
    user_jobname: str | None = None
    user_sysrole_id: UUID


class UserCreate(UserBase):
    user_password: str


class UserUpdate(UserBase):
    user_password: str | None = None


class UserResponse(UserBase):
    user_id: UUID
    signup_completed_status: str
    company_name: str
    position_name: str
    sysrole_name: str

    class Config:
        from_attributes = True


class UserStatusUpdate(BaseModel):
    status: str


# 회사 관련 Pydantic 모델
class CompanyBase(BaseModel):
    company_name: str
    company_scale: str | None = None
    service_startdate: datetime | None = None
    service_enddate: datetime | None = None
    service_status: bool = True


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(CompanyBase):
    pass


class CompanyStatusUpdate(BaseModel):
    service_status: bool
    service_enddate: datetime | None = None


class CompanyResponse(CompanyBase):
    company_id: UUID

    class Config:
        from_attributes = True


# 직급 관련 Pydantic 모델
class PositionBase(BaseModel):
    position_code: str
    position_name: str
    position_detail: str | None = None
    position_company_id: UUID


class PositionCreate(PositionBase):
    pass


class PositionUpdate(PositionBase):
    pass


class PositionResponse(PositionBase):
    position_id: UUID
    position_company_id: UUID

    class Config:
        from_attributes = True

# 관리자 모델
class AdminUserResponse(BaseModel):
    user_id: UUID
    user_name: str
    user_email: EmailStr 
    user_login_id: str
    user_phonenum: str
    user_company_id: UUID
    user_dept_name: str | None = None
    user_team_name: str | None = None
    user_position_id: UUID
    user_jobname: str | None = None
    user_sysrole_id: UUID
    company_name: str | None = None




router = APIRouter()

# 사용자 관리 API
@router.post("/users/", response_model=UserResponse, summary="사용자 생성", status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate):
    """새로운 사용자를 생성합니다."""
    crud = UserCRUD()
    return await crud.create(user.model_dump())

@router.get("/users/admin_users", summary="관리자 목록 조회", response_model=List[AdminUserResponse], dependencies=[Depends(require_super_admin)])
async def list_admin_users(db: AsyncSession = Depends(get_db_session)):
    """관리자 권한을 가진 사용자 목록을 조회합니다."""
    crud = UserCRUD()
    return await crud.get_admin_users(db)

@router.get("/users/{user_id}", summary="특정 사용자 정보 조회", response_model=UserResponse)
async def get_user(user_id: UUID):
    """특정 사용자의 정보를 조회합니다."""
    crud = UserCRUD()
    return await crud.get_by_id(user_id)


@router.get("/users/", summary="사용자 목록 조회", response_model=List[UserResponse], dependencies=[Depends(require_any_admin)])
async def list_users(skip: int = 0, limit: int = 100):
    """사용자 목록을 조회합니다."""
    crud = UserCRUD()
    return await crud.get_all(skip=skip, limit=limit)


@router.put("/users/{user_id}", summary="사용자 정보 수정", response_model=UserResponse)
async def update_user(user_id: UUID, user: UserUpdate):
    """사용자 정보를 수정합니다."""
    crud = UserCRUD()
    return await crud.update(user_id, user.model_dump(exclude_unset=True))

@router.delete("/users/{user_id}", summary="사용자 삭제", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: UUID):
    """사용자를 삭제합니다."""
    crud = UserCRUD()
    await crud.delete(user_id)
    return None


@router.put("/users/{user_id}/status", summary="사용자 승인 상태 변경", response_model=UserResponse)
async def update_user_status(user_id: UUID, status_update: UserStatusUpdate):
    """사용자의 승인 상태를 변경합니다."""
    crud = UserCRUD()
    # 1. 사용자 정보 조회
    user = await crud.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user_name = user["user_name"]
    user_email = user["user_email"]

    # 2. 상태 변경
    updated_user = await crud.update_user_status(user_id, status_update.status)

    # 3. 메일 발송
    await send_user_status_change_email(user_name, user_email, status_update.status)

    return updated_user


@router.get("/users/company/{company_id}", summary="회사별 사용자 목록 조회", response_model=List[UserByCompanyResponse])
async def get_users_by_company(company_id: UUID):
    """
    회사별 사용자 목록 조회
    """
    crud = UserCRUD()
    return await crud.get_users_by_company(company_id)

@router.put("/set_admin/{user_id}", summary="사용자 관리자 권한 위임",)
async def set_admin_user(user_id: UUID, force: bool = False):
    """
    사용자를 관리자 권한으로 지정 (force=True면 기존 관리자 일반 사용자로 변경)
    """
    crud = UserCRUD()
    # 1. 해당 사용자의 회사 ID 조회
    user = await crud.get_by_id(user_id)
    company_id = user["user_company_id"]

    # 2. 해당 회사에 이미 관리자가 있는지 확인
    admin_users = await crud.get_users_by_company(company_id)
    admin_sysrole_id = await crud.get_admin_sysrole_id()
    current_admins = [u for u in admin_users if str(u["user_sysrole_id"]) == str(admin_sysrole_id)]

    if current_admins and not force:
        # 이미 관리자가 있음 → 프론트에 경고 메시지 전달
        return {
            "already_admin": True,
            "message": "이미 이 회사에 관리자가 있습니다.\n선택한 사용자를 관리자로 설정하시겠습니까?"
        }

    # 3. 실제 관리자 지정 (force 옵션 반영)
    result = await crud.set_admin_user(user_id, company_id=company_id, force=force)
    return {"success": result}


# 회사 관리 API
@router.post("/companies/", summary="회사 생성", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_super_admin)])
async def create_company(company: CompanyCreate):
    """새로운 회사를 생성합니다."""
    crud = CompanyCRUD()
    return await crud.create(company.model_dump())


@router.get("/companies/{company_id}", summary="회사 조회", response_model=CompanyResponse, dependencies=[Depends(require_super_admin)])
async def get_company(company_id: UUID):
    """특정 회사의 정보를 조회합니다."""
    crud = CompanyCRUD()
    return await crud.get_by_id(company_id)


@router.get("/companies/", summary="회사 목록 조회", response_model=List[CompanyResponse], dependencies=[Depends(require_super_admin)])
async def list_companies(skip: int = 0, limit: int = 100):
    """회사 목록을 조회합니다."""
    crud = CompanyCRUD()
    return await crud.get_all(skip=skip, limit=limit)


@router.put("/companies/{company_id}", summary="회사 정보 수정", response_model=CompanyResponse, dependencies=[Depends(require_super_admin)])
async def update_company(company_id: UUID, company: CompanyUpdate):
    """회사 정보를 수정합니다."""
    crud = CompanyCRUD()
    return await crud.update(company_id, company.model_dump(exclude_unset=True))


@router.delete("/companies/{company_id}", summary="회사 삭제", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_super_admin)])
async def delete_company(company_id: UUID):
    """회사를 삭제합니다."""
    crud = CompanyCRUD()
    await crud.delete(company_id)
    return None


@router.put("/companies/{company_id}/status", summary="회사 서비스 상태 변경", response_model=CompanyResponse, dependencies=[Depends(require_super_admin)])
async def update_company_status(company_id: UUID, status_update: CompanyStatusUpdate):
    """회사의 서비스 상태를 변경합니다."""
    crud = CompanyCRUD()
    return await crud.update_service_status(
        company_id, 
        status_update.service_status,
        status_update.service_enddate
    )


# 직급 관리 API
@router.post("/positions/", summary="직급 생성", response_model=PositionResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_any_admin)])
async def create_position(position: PositionCreate):
    """새로운 직급을 생성합니다."""
    crud = PositionCRUD()
    return await crud.create(position.model_dump())


@router.get("/positions/{position_id}", summary="직급 정보 조회", response_model=PositionResponse, dependencies=[Depends(require_any_admin)])
async def get_position(position_id: UUID):
    """특정 직급의 정보를 조회합니다."""
    crud = PositionCRUD()
    return await crud.get_by_id(position_id)


@router.get("/positions/", summary="직급 목록 조회", response_model=List[PositionResponse], dependencies=[Depends(require_any_admin)])
async def list_positions(skip: int = 0, limit: int = 100):
    """직급 목록을 조회합니다."""
    crud = PositionCRUD()
    return await crud.get_all(skip=skip, limit=limit)


@router.put("/positions/{position_id}", summary="직급 정보 수정", response_model=PositionResponse, dependencies=[Depends(require_any_admin)])
async def update_position(position_id: UUID, position: PositionUpdate):
    """직급 정보를 수정합니다."""
    crud = PositionCRUD()
    return await crud.update(position_id, position.model_dump(exclude_unset=True))


@router.delete("/positions/{position_id}", summary="직급 삭제", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_any_admin)])
async def delete_position(position_id: UUID):
    """직급을 삭제합니다."""
    crud = PositionCRUD()
    await crud.delete(position_id)
    return None


@router.get("/companies/{company_id}/positions/", summary="특정 회사 직급 목록 조회", response_model=List[PositionResponse])
async def get_company_positions(company_id: UUID):
    """특정 회사의 직급 목록을 조회합니다."""
    crud = PositionCRUD()
    return await crud.get_by_company_id(company_id) 