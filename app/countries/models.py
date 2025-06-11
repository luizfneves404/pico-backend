from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.base import Base


class Country(Base):
    code: Mapped[str] = mapped_column(String(2), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    phone_code: Mapped[str] = mapped_column(String(3))
