from fastapi import APIRouter

from app.api.routes import health, chat, auth, organizations, documents, rag, conversations, approvals, workflows

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(approvals.router, tags=["approvals"])
api_router.include_router(workflows.router, tags=["workflows"])
