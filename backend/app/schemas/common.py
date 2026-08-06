"""
Generic API response envelope, used by every endpoint for a consistent
response shape:

    Success: {"success": true,  "message": "...", "data": {...}}
    Error:   {"success": false, "message": "..."}

The error shape is produced by the exception handlers registered in
main.py (for DomainError, HTTPException, and validation errors) rather
than by route handlers themselves - a route only ever needs to build the
success case.
"""

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class APIResponse(BaseModel, Generic[DataT]):
    success: bool
    message: str
    data: Optional[DataT] = None