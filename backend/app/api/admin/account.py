"""Admin identity endpoint (Phase 9). Mounted under the guarded /api/admin router."""

from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.models import User
from app.schemas.admin import AdminMeResponse
from app.schemas.common import APIResponse

router = APIRouter(tags=["Admin"])


@router.get("/me", response_model=APIResponse[AdminMeResponse], summary="The signed-in administrator")
def admin_me(admin: User = Depends(require_admin)) -> APIResponse[AdminMeResponse]:
    """The admin pages call this to learn, from the server, whether the caller
    really is an administrator. 401 without a login, 403 for a customer."""
    return APIResponse(success=True, message="OK", data=AdminMeResponse.model_validate(admin))
