from fastapi import FastAPI, Request, APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.db_session import get_db_session
from app.services.chatbot_service.scenario import agent
from app.services.chatbot_service.chatbot_agent import run_agent
from app.services.chatbot_service.chatbot_agent_astream import run_agent_stream
from typing import Union
from app.services.chatbot_service.scenario_crud import search_similar_scenario
from langchain.embeddings import HuggingFaceEmbeddings
from fastapi.responses import StreamingResponse

router = APIRouter()

# 임베딩 모델 준비 (1회 초기화)
embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/distiluse-base-multilingual-cased-v2")

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    message: str

class ChatRagResponse(BaseModel):
    match: bool
    scenario_name: str
    content: str
    similarity: float

class ErrorResponse(BaseModel):
    match: bool
    content: str

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    message: str

# @router.post("/chat", response_model=ChatResponse)
# async def chat_endpoint(req: ChatRequest):
#     user_input = req.message
#     response = await agent.arun(user_input)
#     return ChatResponse(message=response)

# @router.post("/chat/embed", response_model=Union[ChatRagResponse, ErrorResponse])
# async def chat_with_vector_search(req: ChatRequest, db: AsyncSession = Depends(get_db_session)):
#     user_input = req.message

#     # 1. 사용자 질문에 대한 임베딩 생성
#     query_embedding = embedding_model.embed_query(user_input)

#     # 2. 유사한 시나리오 검색
#     scenario = await search_similar_scenario(db, query_embedding)

#     if scenario:
#         # 3. 기본 시나리오 응답 내용
#         base_content = scenario.content

#         # 4. agent 도구를 통한 최신 정보 요약 (선택적)
#         try:
#             agent_response = await agent.arun(user_input)
#         except Exception as e:
#             agent_response = f"[에이전트 응답 오류: {e}]"

#         # 5. 두 내용을 합쳐서 반환
#         combined_content = (
#             f"[기본 시나리오 답변]\n{base_content}\n\n"
#             f"[관련 최신 정보]\n{agent_response}"
#         )

#         return ChatRagResponse(
#             match=True,
#             scenario_name=scenario.scenario_name,
#             content=combined_content,
#             similarity=scenario.similarity
#         )
        
#     else:
#         return ErrorResponse(
#             match=False,
#             content="유사한 시나리오를 찾을 수 없습니다."
#         )

@router.post("/chat/0.0.1", summary="챗봇 채팅", response_model=str)
async def chat_endpoint(request: QueryRequest):
    try:
        response = await run_agent(request.query)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# @router.get("/chat/stream")
# async def stream_chat(query: str):
#     async def generate():
#         async for chunk in run_agent_stream(query):
#             yield f"data: {chunk}\n\n"
#         # 스트림 종료 신호
#         yield "data: [DONE]\n\n"
    
#     return StreamingResponse(generate(), media_type="text/event-stream", headers={
#         "Cache-Control": "no-cache",
#         "Connection": "keep-alive",
#     })