from pydantic import BaseModel
from typing import List, Optional

class DashboardSummary(BaseModel):
    title: str
    unit: str
    target: float
    average: float
    labelTarget: str
    labelAvg: str
    color: str
    colorAvg: str
    yMax: int

class ChartData(BaseModel):
    year: str
    feedback_type: str
    count: int
    period: str

class TableData(BaseModel):
    period: str
    feedback_type: str
    filtered_avg: str  # 조회 평균 (필터링된 결과)
    pop: str           # PoP (이전 기간 대비 현재 기간)
    total_avg: str     # 전체 평균
    vs_total: str      # 전체 대비 (조회 평균 vs 전체 평균)

class DashboardResponse(BaseModel):
    summary: List[DashboardSummary]
    chartData: List[ChartData]
    tableData: List[TableData]
    auto_department: Optional[str] = None

class FilterOptions(BaseModel):
    projects: List[dict]
    departments: List[str]
    users: List[dict]


class DashboardFilterProjectOption(BaseModel):
    id: str
    name: str


class DashboardFilterUserOption(BaseModel):
    id: str
    name: str
    login_id: str
    department: Optional[str] = None


class DashboardFilterOptionsResponse(BaseModel):
    projects: List[DashboardFilterProjectOption]
    departments: List[str]
    users: List[DashboardFilterUserOption]
    selected_user_department: Optional[str] = None