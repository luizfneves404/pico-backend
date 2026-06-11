from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import Environment, LocalConfig, settings

router = APIRouter(prefix="/files", tags=["files"])


@router.get(
    "/{file_id}",
    name="get_local_file",
    include_in_schema=settings.environment != Environment.PROD,
)
async def get_file(file_id: str) -> FileResponse:
    """Get a file from local storage (should not be used in production).

    Args:
        file_id: The unique identifier of the file

    Returns:
        FileResponse: The file content

    Raises:
        HTTPException: If the file is not found
    """
    if not isinstance(settings.storage, LocalConfig):
        raise HTTPException(
            status_code=404,
            detail="File serving is only available in local storage mode",
        )

    file_path = Path(settings.storage.base_path) / file_id
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        file_path,
        filename=file_id.split("-", 1)[1] if "-" in file_id else file_id,
    )
