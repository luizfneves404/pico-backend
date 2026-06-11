from pydantic import BaseModel

from app.fcm.models import DeviceType, FCMDevice


class FCMDeviceIn(BaseModel):
    registration_id: str
    device_type: DeviceType


class FCMDeviceOut(BaseModel):
    id: int
    registration_id: str
    device_type: DeviceType

    @classmethod
    def from_orm_model(cls, model: FCMDevice) -> "FCMDeviceOut":
        return cls(
            id=model.id,
            registration_id=model.registration_id,
            device_type=model.device_type,
        )
