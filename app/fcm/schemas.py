from pydantic import BaseModel

from app.fcm.models import DeviceType


class FCMDeviceIn(BaseModel):
    registration_id: str
    type: DeviceType


class FCMDeviceOut(BaseModel):
    id: int
    registration_id: str
    type: DeviceType
