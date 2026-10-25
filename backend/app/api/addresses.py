"""
Address endpoints (Phase 6: list + add).

Every route depends on `get_current_active_user`; the owner is always the
user in the JWT - no route accepts a user id.

    GET     /api/addresses                     the current user's addresses (default first)
    POST    /api/addresses                     add an address
    PATCH   /api/addresses/{id}                edit one (Phase 8)
    DELETE  /api/addresses/{id}                delete one; answers with the addresses that remain (Phase 8)
    POST    /api/addresses/{id}/default        make it the default; answers with the updated list (Phase 8)

Someone else's address id looks exactly like one that does not exist (404).
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models import User
from app.schemas.address import AddressCreateRequest, AddressResponse, AddressUpdateRequest
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


@router.patch(
    "/{address_id}",
    response_model=APIResponse[AddressResponse],
    summary="Edit one of your delivery addresses",
)
def update_address(
    address_id: uuid.UUID,
    payload: AddressUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> APIResponse[AddressResponse]:
    address = service.update_address(current_user.id, address_id, payload)
    return APIResponse(
        success=True,
        message="Address updated.",
        data=AddressResponse.model_validate(address),
    )


@router.post(
    "/{address_id}/default",
    response_model=APIResponse[List[AddressResponse]],
    summary="Make one of your addresses the default",
)
def set_default_address(
    address_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> APIResponse[List[AddressResponse]]:
    addresses = service.set_default(current_user.id, address_id)
    return APIResponse(
        success=True,
        message="Default address updated.",
        data=[AddressResponse.model_validate(a) for a in addresses],
    )


@router.delete(
    "/{address_id}",
    response_model=APIResponse[List[AddressResponse]],
    summary="Delete one of your addresses (orders already placed keep their delivery details)",
)
def delete_address(
    address_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: AddressService = Depends(get_address_service),
) -> APIResponse[List[AddressResponse]]:
    addresses = service.delete_address(current_user.id, address_id)
    return APIResponse(
        success=True,
        message="Address deleted.",
        data=[AddressResponse.model_validate(a) for a in addresses],
    )
