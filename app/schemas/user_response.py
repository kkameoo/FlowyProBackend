from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str


class SignupResponse(BaseModel):
    message: str
    error: str | None = None


class TokenUserResponse(BaseModel):
    sub: str
    id: str
    name: str
    email: str
    login_id: str
    sysrole: str


class LoginResponse(BaseModel):
    authenticated: bool
    user: TokenUserResponse


class JwtLoginResponse(BaseModel):
    access_token: str
    token_type: str


class MeResponse(BaseModel):
    username: str


class AuthCheckResponse(BaseModel):
    authenticated: bool
    user: dict[str, Any]


class ProjectItemResponse(BaseModel):
    userName: str
    projectName: str
    projectId: str
    projectCreatedDate: datetime | None = None
    projectEndDate: datetime | None = None
    projectDetail: str | None = None


class UserProjectsResponse(BaseModel):
    projects: list[ProjectItemResponse]


class CompanyPositionMetaResponse(BaseModel):
    position_id: UUID
    position_company_id: UUID
    position_code: str
    position_name: str
    position_detail: str | None = None


class CompanyMetaResponse(BaseModel):
    company_id: UUID
    company_name: str
    company_scale: str | None = None
    service_startdate: datetime | None = None
    service_enddate: datetime | None = None
    service_status: bool
    company_positions: list[CompanyPositionMetaResponse]


class SysroleMetaResponse(BaseModel):
    sysrole_id: UUID
    sysrole_name: str
    sysrole_detail: str
    permissions: str


class SignupMetaDataResponse(BaseModel):
    companies: list[CompanyMetaResponse]
    sysroles: list[SysroleMetaResponse]


class SignupMetaResponse(SignupMetaDataResponse):
    pass


class MypageCheckResponse(BaseModel):
    verified: bool


class FindIdResponse(BaseModel):
    user_login_id: str


class DuplicateIdCheckResponse(BaseModel):
    is_duplicate: bool
