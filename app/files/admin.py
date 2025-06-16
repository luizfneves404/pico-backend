from typing import Any

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from sqladmin import action
from wtforms import FileField, IntegerField, StringField
from wtforms.validators import Optional

from app.files.models import File
from app.files.storage import storage
from app.shared.admin import CustomModelView


class FileAdmin(CustomModelView, model=File):
    icon = "fa-solid fa-file"
    column_list = [
        File.id,
        File.file_id,
        File.original_name,
        File.created_at,
        File.updated_at,
        File.size,
    ]
    column_searchable_list = [File.id, File.file_id]
    column_sortable_list = [File.id, File.updated_at, File.size]
    column_details_list = [
        File.id,
        File.file_id,
        File.original_name,
        File.created_at,
        File.updated_at,
        File.size,
    ]

    form_overrides = {
        "file_id": FileField,
        "original_name": StringField,
        "size": IntegerField,
    }
    form_args = {
        "file_id": {
            "label": "File",
            "validators": [Optional()],
        },
        "original_name": {
            "validators": [Optional()],
        },
        "size": {
            "validators": [Optional()],
        },
    }
    form_widget_args = {
        "file_id": {
            "required": False,
        },
        "original_name": {
            "readonly": True,
        },
        "size": {
            "readonly": True,
        },
    }

    async def on_model_change(
        self, data: dict[str, Any], model: File, is_created: bool, request: Request
    ) -> None:
        """Handle file upload and create/update File record."""
        # If this is an update and we have a new file, delete the old one
        if not is_created and "file_id" in data and data["file_id"]:
            await run_in_threadpool(storage.delete, model.file_id)

        # Handle new file upload
        if "file_id" in data and data["file_id"]:
            file = data["file_id"]
            file_id = await run_in_threadpool(
                storage.upload,
                file.file,
                file.filename,
            )
            # Update the data dictionary with the string values
            data["file_id"] = file_id
            data["original_name"] = file.filename
            data["size"] = file.size
            # Update the model
            model.file_id = file_id
            model.original_name = file.filename
            model.size = file.size

    @action(
        name="download",
        label="Download",
        add_in_list=True,
        add_in_detail=True,
    )
    async def download(self, request: Request) -> RedirectResponse:
        """Download a file by redirecting to its URL."""
        pks = request.query_params.get("pks", "").split(",")
        if not pks or not pks[0]:
            raise ValueError("No primary key provided")

        # For now, we'll just handle the first file
        # In the future, we could zip multiple files together
        pk = pks[0]
        file: File = await self.get_object_for_details(pk)
        if not file:
            raise ValueError(f"File with id {pk} not found")

        url = await file.get_url()
        return RedirectResponse(url=url)
