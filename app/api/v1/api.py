from fastapi import APIRouter
# from app.api.v1.endpoints import search
from app.api.v1.endpoints import speech_to_text
from app.api.v1.endpoints import docs
from app.api.v1.endpoints import user
from app.api.v1.endpoints import admin
from app.api.v1.endpoints import project
from app.api.v1.endpoints import calendar
from app.api.v1.endpoints import chatbot
from app.api.v1.endpoints import dashboard
from app.api.v1.endpoints import meeting


api_router = APIRouter()
# api_router.include_router(search.router, prefix="/search", tags=["lang_search_test"])
api_router.include_router(speech_to_text.router, prefix="/stt", tags=["speech_to_text"])
api_router.include_router(docs.router, prefix="/docs", tags=["docs"])
api_router.include_router(user.router, prefix="/users", tags=["Users"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(project.router, prefix="/projects", tags=["projects"])
api_router.include_router(calendar.router, prefix="/calendar", tags=["calendar"])
api_router.include_router(chatbot.router, prefix="/chatbot", tags=["chatbot"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(meeting.router, prefix="/meetings", tags=["meetings"])

