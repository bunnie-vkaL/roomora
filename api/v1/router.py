from fastapi import APIRouter
from api.v1.agreements import router as agreements_router
from api.v1.chat import router as chat_router
from api.v1.costs import router as costs_router
from api.v1.discovery import router as discovery_router
from api.v1.rooms import router as rooms_router

api_v1_router = APIRouter(prefix="/v1")

api_v1_router.include_router(discovery_router)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(costs_router)
api_v1_router.include_router(rooms_router)
api_v1_router.include_router(agreements_router)
