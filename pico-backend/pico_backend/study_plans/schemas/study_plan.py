import logging
from datetime import datetime

from ninja import Schema
from pydantic import AwareDatetime, Field

logger = logging.getLogger(__name__)


class StudyPlanOut(Schema):
    id: int
    calendar: dict | None
    created_at: AwareDatetime


class StudyPlanIn(Schema):
    area: str = Field(max_length=255, default="Geral")
