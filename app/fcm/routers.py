import logging

from fastapi import APIRouter

from app.deps import CurrentUserAnnotated, DBSessionAnnotated
from app.fcm import fcm_service
from app.fcm.schemas import FCMDeviceIn, FCMDeviceOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fcm_devices", tags=["fcm_devices"])


@router.post(
    "",
)
async def device_create_or_update(
    device_in: FCMDeviceIn,
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
) -> FCMDeviceOut:
    return FCMDeviceOut.from_orm_model(
        await fcm_service.create_or_update_device(
            db_session,
            current_user.id,
            device_in.registration_id,
            device_in.device_type,
        )
    )
