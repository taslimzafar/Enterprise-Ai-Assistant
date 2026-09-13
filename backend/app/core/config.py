import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Enterprise AI Assistant"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    
    # Environment
    ENVIRONMENT: str = "development"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/enterprise_ai"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Security
    JWT_SECRET: str = "supersecretkey" # Override in production
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    
    # LLM & Embedding Settings
    LLM_PROVIDER: str = "gemini"  # gemini, openai, ollama
    LLM_MODEL: str = "gemini-1.5-flash"
    EMBEDDING_PROVIDER: str = "gemini"  # gemini, openai
    EMBEDDING_MODEL: str = "text-embedding-004"
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    OLLAMA_BASE_URL: Optional[str] = None
    
    # Storage & Vectors
    STORAGE_PATH: str = "./storage"
    VECTOR_DIMENSION: int = 768  # 768 for Gemini text-embedding-004, 1536 for OpenAI
    EMBEDDING_BATCH_SIZE: int = 20

    # RAG & Retrieval Settings
    RAG_TOP_K: int = 5
    RAG_SIMILARITY_THRESHOLD: float = 0.3
    RAG_CONTEXT_CHAR_LIMIT: int = 8000
    RRF_K: int = 60
    HYBRID_VECTOR_WEIGHT: float = 0.7
    HYBRID_KEYWORD_WEIGHT: float = 0.3
    
    # Document Ingestion
    MAX_UPLOAD_SIZE_MB: int = 50
    CHUNK_SIZE: int = 1000  # characters per chunk
    CHUNK_OVERLAP: int = 200  # overlap between chunks
    ALLOWED_DOCUMENT_TYPES: list = ["pdf", "docx", "txt"]
    
    # Agent & Tool Settings
    AGENT_MAX_TOOL_CALLS: int = 5
    TOOL_TIMEOUT_SECONDS: float = 10.0
    
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
