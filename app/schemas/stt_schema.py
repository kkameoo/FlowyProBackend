from pydantic import BaseModel
from uuid import UUID
from typing import List

class ProjectUserItem(BaseModel):
    user_id: UUID
    role_id: UUID
    name: str
    email: str
    user_jobname: str | None = None

class ProjectUsersResponse(BaseModel):
    users: List[ProjectUserItem]

class STTResponse(BaseModel):
    message: str

class MessageResponse(BaseModel):
    message: str

    class Config:
        from_attributes = True