from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional
from datetime import datetime

class CompanyBase(BaseModel):
    company_name: str = Field(..., max_length=150)
    company_scale: Optional[str] = Field(None, max_length=100)
    service_startdate: Optional[datetime]
    service_enddate: Optional[datetime]
    service_status: bool

class CompanyCreate(CompanyBase):
    pass

class CompanyUpdate(CompanyBase):
    pass

class CompanyRead(CompanyBase):
    company_id: UUID

class Config:
        from_attributes = True  # ORM 객체 → Pydantic 변환에 필수

    