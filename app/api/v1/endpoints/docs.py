from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel
from typing import List, Optional, Annotated, Any, Dict
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.db_session import get_db_session
from app.models.interdoc import Interdoc
from app.services.docs_service.docs_recommend import run_doc_recommendation, get_document_download_link
from app.services.docs_service.docs_crud import (
    create_document,
    update_document,
    get_documents,
    get_document,
    delete_document
)
from app.services.admin_service.admin_check import require_company_admin
from sqlalchemy.orm import Session
from app.services.docs_service.docs_crud import get_db
from sqlalchemy import select
from app.services.docs_service.draft_log_crud import get_draft_logs_by_meeting_id
from app.schemas.meeting import DraftLogResponse
from app.services.docs_service.orchestration import super_agent_for_meeting
from app.schemas.docs_schema import DeleteResponse, DownloadLinkResponse

router = APIRouter()

# 요청/응답 모델
class DocumentRecommendRequest(BaseModel):
    query: str

class Document(BaseModel):
    title: str
    download_url: str
    relevance_reason: str

class DocumentRecommendResponse(BaseModel):
    documents: List[Document]

class DocumentResponse(BaseModel):
    interdocs_id: UUID
    interdocs_type_name: str
    interdocs_filename: str
    interdocs_contents: str
    interdocs_path: str
    interdocs_uploaded_date: datetime
    interdocs_updated_date: Optional[datetime]
    interdocs_update_user_id: UUID

    class Config:
        from_attributes = True

class SuperAgentRequest(BaseModel):
    meeting_text: str
    meeting_id: Optional[str] = None

@router.post("/recommend", response_model=Dict[str, Any], summary="문서 추천", dependencies=[Depends(require_company_admin)])
async def recommend_documents_route(request: DocumentRecommendRequest):
    """
    역할 또는 업무 내용을 기반으로 관련 문서를 추천합니다.
    - **query**: 검색할 역할 또는 업무 내용
    """
    try:
        result = await run_doc_recommendation(request.query)
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"문서 추천 중 오류 발생: {str(e)}"
        )

@router.post("/", summary="문서 생성", response_model=DocumentResponse)
async def create_new_document(
    update_user_id: Annotated[UUID, Form(description="업로드 사용자 ID")],
    doc_type: Annotated[str, Form(description="문서 유형")],
    file: UploadFile = File(description="업로드할 파일"),
    db: Session = Depends(get_db)
):
    """
    새로운 문서를 업로드합니다.
    
    - **doc_type**: 문서 유형
    - **file**: 업로드할 파일
    - **update_user_id**: 업로드 사용자 ID
    """
    return await create_document(db, file, doc_type, update_user_id)

@router.put("/{doc_id}", summary="문서 수정", response_model=DocumentResponse)
async def update_existing_document(
    doc_id: UUID,
    update_user_id: Annotated[UUID, Form(description="수정 사용자 ID")],
    file: UploadFile = File(description="새로운 파일"),
    db: Session = Depends(get_db)
):
    """
    기존 문서를 수정합니다.
    
    - **doc_id**: 수정할 문서 ID
    - **file**: 새로운 파일
    - **update_user_id**: 수정 사용자 ID
    """
    return await update_document(db, doc_id, file, update_user_id)

@router.get("/", response_model=List[DocumentResponse], summary="모든 문서 목록 조회", dependencies=[Depends(require_company_admin)])
async def get_all_documents(
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db)
):
    """
    문서 목록을 조회합니다.
    
    - **skip**: 건너뛸 문서 수
    - **limit**: 조회할 문서 수
    """
    return await get_documents(db, skip, limit)

@router.get("/{doc_id}", summary="문서 조회", response_model=DocumentResponse)
async def get_single_document(
    doc_id: UUID,
    db: Session = Depends(get_db)
):
    """
    단일 문서를 조회합니다.
    
    - **doc_id**: 조회할 문서 ID
    """
    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    return doc

@router.delete("/{doc_id}", summary="문서 삭제", response_model=DeleteResponse)
async def delete_existing_document(
    doc_id: UUID,
    db: Session = Depends(get_db)
):
    """
    문서를 삭제합니다.
    
    - **doc_id**: 삭제할 문서 ID
    """
    result = await delete_document(db, doc_id)
    if result:
        return {"message": "문서가 성공적으로 삭제되었습니다"}
    raise HTTPException(status_code=500, detail="문서 삭제 중 오류가 발생했습니다")


@router.get("/download/{interdocs_id}", summary="문서 다운로드 링크 조회", response_model=DownloadLinkResponse)
async def get_doc_download_link(interdocs_id: UUID, db: AsyncSession = Depends(get_db_session)):
    # 기존 코드 그대로...
    result = await db.execute(select(Interdoc.interdocs_path).where(Interdoc.interdocs_id == interdocs_id))
    interdocs_path = result.scalar_one_or_none()
    if not interdocs_path:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    link = await get_document_download_link(interdocs_path)
    return {"download_url": link}

@router.get("/draft-logs/by-meeting/{meeting_id}", summary="draft_log 목록 조회", response_model=List[DraftLogResponse])
async def get_draft_logs_by_meeting(
    meeting_id: str,
    db: AsyncSession = Depends(get_db_session)
):
    """
    meeting_id로 draft_log 목록을 조회합니다.
    """
    draft_logs = await get_draft_logs_by_meeting_id(db, meeting_id)
    return draft_logs

@router.post("/super-agent", summary="문서 추천 에이전트",)
async def run_super_agent(
    req: SuperAgentRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    회의 텍스트를 분석하여 내부 문서 추천 에이전트 결과를 반환합니다.
    - meeting_text: 회의 내용 (str)
    - meeting_id: (선택) DB 저장용 meeting_id
    """
    result = await super_agent_for_meeting(req.meeting_text, db=db, meeting_id=req.meeting_id)
    return {"result": result}