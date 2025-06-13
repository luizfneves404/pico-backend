from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import Select

from app.config import settings

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Pagination parameters for API endpoints.

    Attributes:
        page: The page number to retrieve (1-based)
        size: Number of items per page
    """

    page: int = Field(1, ge=1, description="Page number (1-based)")
    size: int = Field(
        settings.pagination_per_page,
        ge=1,
        description="Number of items per page",
    )


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    size: int


def paginate(
    items: list[T],
    pagination: PaginationParams,
) -> PaginatedResponse[T]:
    """Paginate a list of items.

    Args:
        items: List of items to paginate
        pagination: Pagination parameters

    Returns:
        Dictionary containing paginated results and total count
    """
    return PaginatedResponse(
        items=items,
        page=pagination.page,
        size=pagination.size,
    )


def paginate_memory(
    items: list[T],
    pagination: PaginationParams,
) -> PaginatedResponse[T]:
    """Paginate a list of items in memory."""
    offset = (pagination.page - 1) * pagination.size
    items = items[offset : offset + pagination.size]
    return PaginatedResponse(items=items, page=pagination.page, size=pagination.size)


def paginate_query(
    query: Select[tuple[T]],
    pagination: PaginationParams,
) -> Select[tuple[T]]:
    """Paginate a database query."""
    return query.offset((pagination.page - 1) * pagination.size).limit(pagination.size)


def get_pagination_params(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    size: int = Query(
        settings.pagination_per_page,
        ge=1,
        description="Number of items per page",
    ),
) -> PaginationParams:
    """FastAPI dependency for getting pagination parameters from query.

    Args:
        page: Page number from query
        size: Page size from query

    Returns:
        PaginationParams object
    """
    return PaginationParams(page=page, size=size)
