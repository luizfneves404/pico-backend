from pydantic import BaseModel, Field


class SchoolIn(BaseModel):
    name: str = Field(..., min_length=1)


class SchoolOut(BaseModel):
    id: int
    name: str
