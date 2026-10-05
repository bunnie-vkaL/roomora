from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from core.services import DomainError
from api.v1.router import api_v1_router

api_app = FastAPI(
    title="ROOMORA API",
    version="1.0.0",
    description="Mobile-first roommate matching & collaborative search API for Hanoi.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api_app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    return JsonResponse(
        status_code=exc.status,
        content={"detail": exc.message},
    )


@api_app.get("/health")
def health_check():
    return {"status": "ok", "service": "Roomora API"}


api_app.include_router(api_v1_router)
