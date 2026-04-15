from pydantic import BaseModel, EmailStr
from uuid import UUID


class UserByCompanyResponse(BaseModel):
    user_id: UUID
    user_login_id: str
    user_email: EmailStr
    user_name: str
    user_phonenum: str
    user_company_id: UUID
    user_dept_name: str | None = None
    user_team_name: str | None = None
    user_position_id: UUID
    user_jobname: str | None = None
    user_sysrole_id: UUID