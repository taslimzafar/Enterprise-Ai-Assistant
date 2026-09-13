import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from app.core.config import settings

router = APIRouter()

# Initialize OpenAI client with settings (or placeholder if not configured)
client = None
if settings.OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception:
        client = None

class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    question: str
    answer: str

@router.post("/ask", response_model=ChatResponse)
async def ask_ai(request: ChatRequest):
    """
    Basic endpoint to ask a question (migrated from main.py).
    """
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI client not configured or missing API key")
    response = client.responses.create(
        model="gpt-5.6-luna",
        input=request.question
    )

    return ChatResponse(
        question=request.question,
        answer=response.output_text
    )
