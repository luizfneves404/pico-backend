from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.countries.models import Country


class CountryNotFound(Exception):
    pass


async def get_country(db_session: AsyncSession, country_code: str) -> Country:
    country = await db_session.scalar(
        select(Country).where(Country.code == country_code)
    )
    if not country:
        raise CountryNotFound(f"Country with code {country_code} not found")
    return country
