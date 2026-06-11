import logging

import api.services.fcm_service as fcm_service
from api.schemas.fcm_devices import FCMDeviceIn, FCMDeviceOut
from ninja import Router

logger = logging.getLogger(__name__)

router = Router()


@router.post(
    "",
    response={201: FCMDeviceOut},
    url_name="device_create_or_update",
)
async def device_create_or_update(request, device_in: FCMDeviceIn):
    user = request.auth
    return await fcm_service.create_or_update_device(
        user,
        device_in.registration_id,
        device_in.type,
    )
