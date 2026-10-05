from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    detail: str
    code: Optional[str] = None


class StandardResponse(BaseModel):
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None
