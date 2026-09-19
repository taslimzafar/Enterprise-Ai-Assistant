from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.core.config import settings
from app.core.logging import logger
from app.api.main import api_router

def create_app() -> FastAPI:
    """
    Application factory pattern to create and configure the FastAPI app.
    """
    logger.info(f"Starting {settings.PROJECT_NAME} in {settings.ENVIRONMENT} mode.")
    
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Agentic Knowledge & Workflow Assistant",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
    )

    # Security Headers Middleware
    from app.core.security_headers import SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)

    # Content-Length Limit Middleware to protect against resource exhaustion
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request

    class ContentLengthLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Enforce body limit for standard JSON/REST endpoints; documents upload endpoint enforces MAX_UPLOAD_SIZE_MB natively
            if "/documents" not in request.url.path:
                content_length = request.headers.get("content-length")
                if content_length:
                    try:
                        length = int(content_length)
                        if length > settings.MAX_REQUEST_BODY_BYTES:
                            return Response(
                                content="Payload Too Large: Request body exceeds permitted size limit.",
                                status_code=413,
                                media_type="text/plain",
                            )
                    except ValueError:
                        pass
            return await call_next(request)

    app.add_middleware(ContentLengthLimitMiddleware)

    # Set up CORS middleware with explicit configured origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Include main API router
    app.include_router(api_router, prefix=settings.API_V1_STR)

    @app.get("/")
    def root():
        return {
            "message": f"{settings.PROJECT_NAME} API is running!",
            "docs": f"{settings.API_V1_STR}/docs"
        }

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return Response(content=b"", media_type="image/x-icon")
        
    return app

app = create_app()