"""
Address endpoints (Phase 6: list + add).

Every route depends on `get_current_active_user`; the owner is always the
user in the JWT - no route accepts a user id.

    GET   /api/addresses     the current user's addresses (default first)
    POST  /api/addresses     add an address

Editing, deleting and changing the default arrive in Phase 8.
"""

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models import User
from app.schemas.address import AddressCreateRequest, AddressResponse
from app.schemas.common import APIResponse
from app.services.address_service import AddressService

router = APIRouter(prefix="/api/addresses", tags=["Addresses"])


def get_address_service(db: Session = Depends(get_db)) -> AddressService:
    return AddressService(db)


@router.get(
    "",
    response_model=APIResponse[List[AddressResponse]],
    status_code=status.HTTP_200_OK,
    summary="List the current user's delivery addresses",
)
def list_addresses(
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> APIResponse[List[AddressResponse]]:
    addresses = service.list_addresses(current_user.id)
    return APIResponse(
        success=True,
        message="Addresses retrieved.",
        data=[AddressResponse.model_validate(a) for a in addresses],
    )


@router.post(
    "",
    response_model=APIResponse[AddressResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add a delivery address",
)
def create_address(
    payload: AddressCreateRequest,
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> APIResponse[AddressResponse]:
    address = service.create_address(current_user.id, payload)
    return APIResponse(
        success=True,
        message="Address added.",
        data=AddressResponse.model_validate(address),
    )