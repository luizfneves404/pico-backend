import csv
import io
import zipfile
from typing import Any, ClassVar

from fastapi import Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator
from sqladmin import action
from wtforms import DateTimeField, Field, FileField, IntegerField, StringField
from wtforms.validators import Optional

from app.files.models import File
from app.files.storage import storage
from app.shared.admin import CustomModelView


class FileImportRecord(BaseModel):
    """Individual file record from CSV manifest."""

    filename: str
    original_name: str | None = None

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate filename is safe."""
        # Basic safety checks
        if not v or v.startswith(".") or "/" in v or "\\" in v:
            raise ValueError(f"Invalid filename: {v}")
        if len(v) > 255:
            raise ValueError("Filename too long")
        return v

    def get_safe_filename(self) -> str:
        """Get the filename to use for storage."""
        return self.original_name or self.filename


class FileImportSchema(BaseModel):
    """Schema for file import - either zip upload or direct files."""

    zip_file: UploadFile | None = None
    csv_manifest: str | None = None
    direct_files: list[UploadFile] | None = None

    @field_validator("csv_manifest")
    @classmethod
    def validate_csv(cls, v: str | None) -> str | None:
        """Validate CSV manifest format."""
        if v is None:
            return v

        # Parse and validate CSV structure
        try:
            reader = csv.DictReader(io.StringIO(v))
            required_fields = {"filename"}

            if not reader.fieldnames or not required_fields.issubset(
                set(reader.fieldnames)
            ):
                raise ValueError('CSV must have "filename" column')

            # Validate each row
            records = list(reader)
            if not records:
                raise ValueError("CSV manifest cannot be empty")

            for i, row in enumerate(records):
                try:
                    FileImportRecord(**row)
                except Exception as e:
                    raise ValueError(f"Invalid CSV row {i + 1}: {e}") from e

        except Exception as e:
            raise ValueError(f"Invalid CSV format: {e}") from e

        return v

    def parse_csv_manifest(self) -> list[FileImportRecord]:
        """Parse CSV manifest into FileImportRecord objects."""
        if not self.csv_manifest:
            return []

        reader = csv.DictReader(io.StringIO(self.csv_manifest))
        return [FileImportRecord(**row) for row in reader]


class FileAdmin(CustomModelView, model=File):
    icon = "fa-solid fa-file"
    column_list = (
        File.id,
        File.file_id,
        File.original_name,
        File.created_at,
        File.updated_at,
        File.size,
    )
    column_searchable_list = (File.id, File.file_id)
    column_sortable_list = (File.id, File.updated_at, File.size)
    column_details_list = (
        File.id,
        File.file_id,
        File.original_name,
        File.created_at,
        File.updated_at,
        File.size,
    )

    form_overrides: ClassVar[dict[str, type[Field]]] = {
        "file_id": FileField,
        "original_name": StringField,
        "size": IntegerField,
        "updated_at": DateTimeField,
        "created_at": DateTimeField,
    }
    form_args: ClassVar[dict[str, dict[str, Any]]] = {
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
        "updated_at": {
            "validators": [Optional()],
        },
        "created_at": {
            "validators": [Optional()],
        },
    }
    form_widget_args: ClassVar[dict[str, dict[str, Any]]] = {
        "file_id": {
            "required": False,
        },
        "original_name": {
            "required": False,
        },
        "size": {
            "required": False,
        },
        "updated_at": {
            "readonly": True,
        },
        "created_at": {
            "readonly": True,
        },
    }

    form_create_rules: ClassVar[list[str]] = ["file_id", "original_name", "size"]

    # Import functionality
    can_import = True
    import_schema = FileImportSchema
    import_template_data: ClassVar = {
        "zip_file": "Upload a ZIP file containing files to import",
        "csv_manifest": "filename,original_name\ndocument1.pdf,My Document.pdf\nimage.jpg,Profile Image.jpg",
        "direct_files": "Or upload files directly (for small batches)",
    }

    async def on_model_change(
        self,
        data: dict[str, Any],
        model: File,
        is_created: bool,
        request: Request,  # noqa: ARG002
    ) -> None:
        """Handle file upload and create/update File record."""
        # If this is an update and we have a new file, delete the old one
        if not is_created and "file_id" in data and data["file_id"]:
            await run_in_threadpool(storage.delete, model.file_id)

        # Handle new file upload
        if data.get("file_id"):
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

    async def to_orm_model(
        self, validated_data_list: list[FileImportSchema]
    ) -> list[File]:
        """Convert import data to File ORM models by processing uploaded files."""
        files: list[File] = []

        for validated_data in validated_data_list:
            if validated_data.zip_file and validated_data.csv_manifest:
                # Process zip file with CSV manifest
                zip_files = await self.process_zip_import(
                    validated_data.zip_file, validated_data.parse_csv_manifest()
                )
                files.extend(zip_files)

            elif validated_data.direct_files:
                # Process direct file uploads
                direct_files = await self.process_direct_import(
                    validated_data.direct_files
                )
                files.extend(direct_files)

            else:
                raise ValueError(
                    "Either zip_file+csv_manifest or direct_files must be provided"
                )

        return files

    async def process_zip_import(
        self, zip_upload: UploadFile, manifest: list[FileImportRecord]
    ) -> list[File]:
        """Process zip file import with CSV manifest."""
        files: list[File] = []

        # Read zip file content
        zip_content = await zip_upload.read()

        def _process_zip() -> dict[str, tuple[bytes, FileImportRecord]]:
            with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zip_file:
                # Security check: validate zip file
                self.validate_zip_file(zip_file)

                extracted_files: dict[str, tuple[bytes, FileImportRecord]] = {}
                for record in manifest:
                    if record.filename not in zip_file.namelist():
                        raise ValueError(f"File '{record.filename}' not found in zip")

                    # Extract file content
                    file_content = zip_file.read(record.filename)
                    extracted_files[record.filename] = (file_content, record)

                return extracted_files

        extracted_files = await run_in_threadpool(_process_zip)

        # Upload each file to storage and create File records
        for content, record in extracted_files.values():
            file_id = await run_in_threadpool(
                storage.upload,
                io.BytesIO(content),
                record.get_safe_filename(),
            )

            file = File(
                file_id=file_id,
                original_name=record.get_safe_filename(),
                size=len(content),
            )
            files.append(file)

        return files

    async def process_direct_import(self, upload_files: list[UploadFile]) -> list[File]:
        """Process direct file uploads."""
        files: list[File] = []

        for upload_file in upload_files:
            # Validate file
            self.validate_upload_file(upload_file)

            # Upload to storage
            file_id = await run_in_threadpool(
                storage.upload,
                upload_file.file,
                upload_file.filename or "uploaded_file",
            )

            file = File(
                file_id=file_id,
                original_name=upload_file.filename or "uploaded_file",
                size=upload_file.size,
            )
            files.append(file)

        return files

    def validate_zip_file(self, zip_file: zipfile.ZipFile) -> None:
        """Validate zip file for security."""
        # Check for zip bombs and path traversal
        total_size = 0
        max_size = 100 * 1024 * 1024  # 100MB limit
        max_files = 1000

        if len(zip_file.namelist()) > max_files:
            raise ValueError(f"Too many files in zip (max {max_files})")

        for file_info in zip_file.infolist():
            # Check for path traversal
            if file_info.filename.startswith("/") or ".." in file_info.filename:
                raise ValueError(f"Unsafe file path: {file_info.filename}")

            # Check file size
            total_size += file_info.file_size
            if total_size > max_size:
                raise ValueError(
                    f"Zip file too large (max {max_size // 1024 // 1024}MB)"
                )

            # Check compression ratio (zip bomb detection)
            if file_info.file_size > 0:
                compression_ratio = file_info.compress_size / file_info.file_size
                if compression_ratio < 0.01:  # Highly compressed
                    raise ValueError(
                        f"Suspicious compression ratio in {file_info.filename}"
                    )

    def validate_upload_file(self, upload_file: UploadFile) -> None:
        """Validate individual upload file."""
        max_size = 50 * 1024 * 1024  # 50MB per file

        if upload_file.size and upload_file.size > max_size:
            raise ValueError(
                f"File too large: {upload_file.filename} ({upload_file.size} bytes)"
            )

        if not upload_file.filename:
            raise ValueError("File must have a filename")

        # Basic filename validation
        if upload_file.filename.startswith(".") or "/" in upload_file.filename:
            raise ValueError(f"Invalid filename: {upload_file.filename}")

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
        file: File = await self._get_object_by_pk(self._stmt_by_identifier(pk))  # pyright: ignore[reportUnknownMemberType]
        if not file:
            raise ValueError(f"File with id {pk} not found")

        url = await file.get_url()
        return RedirectResponse(url=url)
