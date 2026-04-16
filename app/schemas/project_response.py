from typing import Any
from uuid import UUID
from pydantic import BaseModel
from app.schemas.project import UserSchema, RoleSchema


class ProjectCreateResponse(BaseModel):
    project_id: UUID


class MessageResponse(BaseModel):
    message: str


class MeetingCreateResponse(BaseModel):
    meeting_id: UUID


class ProjectMetaResponse(BaseModel):
    company_id: UUID
    users: list[UserSchema]
    roles: list[RoleSchema]


class GenericListResponse(BaseModel):
    data: list[Any]


class GenericObjectResponse(BaseModel):
    data: Any
