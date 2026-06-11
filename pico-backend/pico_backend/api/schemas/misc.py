from ninja import Schema
from pydantic import ConfigDict


class CommandOut(Schema):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str
