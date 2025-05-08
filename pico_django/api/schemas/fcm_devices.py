from ninja.schema import Schema
from pydantic import field_validator


class FCMDeviceIn(Schema):
    registration_id: str
    type: str

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str):
        types = ["web", "ios", "android"]
        if v not in types:
            raise ValueError(f"choice must be one of {types}")
        return v


class FCMDeviceOut(Schema):
    id: int
    registration_id: str
    type: str
