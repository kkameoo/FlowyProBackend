from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import Company, Sysrole


# 회사 목록과 시스템 역할 목록 함께 조회 (조인 없이)
async def get_signup_meta(db: AsyncSession):
    # 회사 + 직급 로딩
    stmt_company = (
        select(Company)
        .options(selectinload(Company.company_positions))
    )
    company_result = await db.execute(stmt_company)
    companies = company_result.scalars().all()

    # 시스템 역할 로딩
    stmt_sysrole = select(Sysrole)
    sysrole_result = await db.execute(stmt_sysrole)
    sysroles = sysrole_result.scalars().all()

    company_items = []
    for company in companies:
        positions = []
        for position in company.company_positions:
            positions.append(
                {
                    "position_id": position.position_id,
                    "position_company_id": position.position_company_id,
                    "position_code": position.position_code,
                    "position_name": position.position_name,
                    "position_detail": position.position_detail,
                }
            )

        company_items.append(
            {
                "company_id": company.company_id,
                "company_name": company.company_name,
                "company_scale": company.company_scale,
                "service_startdate": company.service_startdate,
                "service_enddate": company.service_enddate,
                "service_status": company.service_status,
                "company_positions": positions,
            }
        )

    sysrole_items = [
        {
            "sysrole_id": sysrole.sysrole_id,
            "sysrole_name": sysrole.sysrole_name,
            "sysrole_detail": sysrole.sysrole_detail,
            "permissions": sysrole.permissions,
        }
        for sysrole in sysroles
    ]

    return {"companies": company_items, "sysroles": sysrole_items}
