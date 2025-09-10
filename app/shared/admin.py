import copy
import csv
import io
import json
import logging
import re
from collections.abc import Callable
from typing import Any, ClassVar, TypeVar, cast

from fastapi import HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from geoalchemy2 import Geography
from markupsafe import Markup
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import (
    ColumnProperty,
    DeclarativeBase,
    InstrumentedAttribute,
)
from starlette.datastructures import UploadFile
from wtforms import StringField

from app.base import resync_autoincrement
from app.shared.bootstrap_sqladmin import monkey_patch_sqladmin

monkey_patch_sqladmin()  # it is necessary to run this before importing sqladmin.
# add sqladmin imports below!!!
from sqladmin import ModelView  # noqa: E402
from sqladmin.application import Admin as SQLAdminAdmin  # noqa: E402
from sqladmin.forms import (  # noqa: E402
    ModelConverter,
    converts,  # pyright: ignore[reportUnknownVariableType]
)

type MODEL_ATTR = str | InstrumentedAttribute[Any]

ModelType = TypeVar("ModelType", bound=DeclarativeBase)

WKT_RE = re.compile(r"^POINT\(\s*([-0-9\.]+)\s+([-0-9\.]+)\s*\)$")

logger = logging.getLogger(__name__)


def bool_formatter(value: bool) -> Markup:
    """Return check icon if value is `True` or X otherwise."""
    icon_class = "fa-check text-success" if value else "fa-times text-danger"
    return Markup(f"<i class='fa {icon_class}'></i>")


class ImportResult(BaseModel):
    """Simple import result with clear error messages."""

    total_rows: int
    successful_rows: int
    failed_rows: int
    errors: list[dict[str, Any]]


class CSVImportError(Exception):
    """Exception raised during CSV import operations."""

    pass


class AdminWithImport(SQLAdminAdmin):
    def _find_custom_model_view(self, identity: str) -> "CustomModelView":
        for view in self.views:
            if isinstance(view, CustomModelView) and view.identity == identity:
                return view
        raise HTTPException(status_code=404)

    async def import_csv(self, request: Request) -> HTMLResponse | Response:
        """Main import endpoint - handles both form display and file processing."""
        model_view = self._find_custom_model_view(request.path_params["identity"])

        if not model_view.can_import or not model_view.is_accessible(request):
            raise HTTPException(status_code=403)

        if not model_view.import_schema:
            raise CSVImportError("No import schema configured for this model")

        headers = list(model_view.import_schema.model_fields.keys())  # type: ignore

        if request.method == "GET":
            context = {
                "model_view": model_view,
                "model_name": model_view.model.__name__,
                "sample_columns": headers,
                "max_rows": model_view.import_max_rows,
                "is_file_upload": model_view.is_file_upload_schema(),
                "template_data": model_view.import_template_data,
            }
            return await self.templates.TemplateResponse(
                request, "sqladmin/import.html", context
            )

        elif request.method == "POST":
            return await self._handle_import_upload(request, model_view)
        else:
            raise HTTPException(status_code=405, detail="Method not allowed")

    async def import_template(self, request: Request) -> Response:
        """Download CSV template endpoint."""
        model_view = self._find_custom_model_view(request.path_params["identity"])

        if not model_view.can_import or not model_view.is_accessible(request):
            raise HTTPException(status_code=403)

        csv_content = model_view.generate_import_template()

        filename = f"{model_view.model.__name__.lower()}_import_template.csv"

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    async def _handle_import_upload(
        self,
        request: Request,
        model_view: "CustomModelView",
    ) -> HTMLResponse:
        """Handle CSV file upload and processing."""
        form = await request.form()
        dry_run = form.get("dry_run") == "true"

        if model_view.is_file_upload_schema():
            # Handle file upload schema
            result = await self._handle_file_upload_import(form, model_view, dry_run)
        else:
            # Handle traditional CSV import
            result = await self._handle_csv_import(form, model_view, dry_run)

        cleaned_data = copy.deepcopy(result.errors)
        for error in cleaned_data:
            # Handle different types of data structures in error["data"]
            if isinstance(error["data"], list):
                for data in error["data"]:
                    # Only process if data is a dictionary
                    if isinstance(data, dict):
                        for key, value in data.items():
                            if isinstance(value, UploadFile):
                                data[key] = f"UploadFile(filename='{value.filename}')"
                            elif isinstance(value, list):
                                data[key] = [
                                    (
                                        f"UploadFile(filename='{item.filename}')"
                                        if isinstance(item, UploadFile)
                                        else item
                                    )
                                    for item in cast("list[Any]", value)
                                ]
                    # If data is not a dict (e.g., string), leave it as is
            elif isinstance(error["data"], dict):
                # Handle case where error["data"] is a single dictionary
                for key, value in error["data"].items():
                    if isinstance(value, UploadFile):
                        error["data"][key] = f"UploadFile(filename='{value.filename}')"
                    elif isinstance(value, list):
                        error["data"][key] = [
                            (
                                f"UploadFile(filename='{item.filename}')"
                                if isinstance(item, UploadFile)
                                else item
                            )
                            for item in cast("list[Any]", value)
                        ]
            # If error["data"] is neither list nor dict (e.g., string), leave it as is

        result.errors = cleaned_data

        context = {
            "model_view": model_view,
            "model_name": model_view.model.__name__,
            "result": result,
            "dry_run": dry_run,
        }

        return await self.templates.TemplateResponse(
            request, "sqladmin/import_result.html", context
        )

    async def _handle_csv_import(
        self, form: Any, model_view: "CustomModelView", dry_run: bool
    ) -> ImportResult:
        """Handle traditional CSV import."""
        file = form.get("csv_file")

        if not file or not isinstance(file, UploadFile):
            raise HTTPException(status_code=400, detail="No file uploaded")

        if not file.filename or not file.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="File must be a CSV file")

        file_content = await file.read()
        try:
            content = file_content.decode("utf-8")
            csv_reader = csv.DictReader(io.StringIO(content))
            rows = list(csv_reader)

        except UnicodeDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail="Invalid file encoding. Please use UTF-8 encoded CSV files.",
            ) from e
        except csv.Error as e:
            raise HTTPException(
                status_code=400, detail=f"Error parsing CSV file: {e!s}"
            ) from e

        return await model_view.import_data(rows, dry_run=dry_run)

    async def _handle_file_upload_import(
        self, form: Any, model_view: "CustomModelView", dry_run: bool
    ) -> "ImportResult":
        """Handle file upload import (zip files, direct uploads, etc.)."""
        # Build form data matching the schema
        form_data: dict[str, Any] = {}

        if not model_view.import_schema:
            raise HTTPException(status_code=500, detail="No import schema configured")

        import_schema = model_view.import_schema  # Type narrowing
        for field_name, field_info in import_schema.model_fields.items():
            annotation_str = str(field_info.annotation)

            if "UploadFile" in annotation_str and "list" not in annotation_str:
                # Handle single file upload
                file_value = form.get(field_name)
                if isinstance(file_value, UploadFile) and file_value.filename:
                    form_data[field_name] = file_value
                else:
                    form_data[field_name] = None

            elif "UploadFile" in annotation_str and "list" in annotation_str:
                # Handle multiple file uploads
                file_values = form.getlist(field_name)
                upload_files = [
                    f for f in file_values if isinstance(f, UploadFile) and f.filename
                ]
                # Assigning an empty list is often better for type-hinted list fields
                form_data[field_name] = upload_files

            else:
                # Handle regular form fields (text, etc.)
                form_data[field_name] = form.get(field_name)

                # Validate and process using the schema
        try:
            validated_data = import_schema.model_validate(form_data)
            return await model_view.import_file_data([validated_data], dry_run=dry_run)
        except ValidationError as e:
            # Convert validation errors to ImportResult format
            result = ImportResult(
                total_rows=1,
                successful_rows=0,
                failed_rows=1,
                errors=[],
            )
            for error in e.errors():
                error_field_name = str(error["loc"][0]) if error["loc"] else "unknown"
                # Get field info for error reporting
                error_field_info = import_schema.model_fields.get(error_field_name)
                expected_type = (
                    str(error_field_info.annotation) if error_field_info else "unknown"
                )

                result.errors.append(
                    {
                        "row": 1,
                        "field": error_field_name,
                        "message": error["msg"],
                        "input_value": form_data.get(error_field_name, "N/A"),
                        "expected_type": expected_type,
                        "data": form_data,
                    }
                )
            return result


class LocationField(StringField):
    """
    Renders as a text box containing e.g. "POINT(-46.633  -23.550)"
    but you can customize the widget to render two floats if you like.
    """

    def process_formdata(self, valuelist):
        # valuelist is a single-item list: [ "POINT(lon lat)" ]
        if not valuelist:
            self.data = None
            return

        text = valuelist[0].strip()
        if not text:
            self.data = None
            return

        m = WKT_RE.match(text)
        if not m:
            raise ValueError("Must be WKT like: POINT(lon lat)")
        self.data = text  # SQLAdmin will pass this string as $param

    def _value(self):
        # When rendering the form, show whatever string we have
        return self.data or ""


class CustomFormConverter(ModelConverter):
    @converts("geoalchemy2.types.Geography")
    def conv_location(
        self,
        _model: type,
        _prop: ColumnProperty[Geography],
        kwargs: dict[str, Any],
    ) -> LocationField:
        return LocationField(**kwargs)


def serialize_for_csv(value: Any) -> str:
    """Serialize any value to a CSV-safe string with explicit type handling."""
    if value is None:
        return ""  # Empty string for None/null values
    elif isinstance(value, bool):
        return "true" if value else "false"  # JSON boolean format
    elif isinstance(value, int | float):
        return str(value)
    elif isinstance(value, str):
        return value
    elif isinstance(value, list | dict):
        return json.dumps(value)
    else:
        # Fallback for other types (datetime, etc.)
        return json.dumps(value, default=str)


def parse_field_value(value: str | None) -> Any:
    """Parse a CSV string value with explicit type conversion rules.

    Special handling for empty strings vs None:
    - Empty CSV cell (None from CSV reader) -> None
    - Cell with just quotes '""' -> empty string ""
    - Cell with 'null' -> None
    """
    if value is None:
        return None
    if value == '""':
        return ""
    if not value or value.strip() == "":
        return None

    value = value.strip()

    # null marker
    if value.lower() == "null":
        return None

    # booleans
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    # JSON objects/arrays
    if value.startswith(("{", "[")):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            pass

    # 🛑 DO NOT coerce to number here, let pydantic handle it
    return value  # Always return string unless JSON, bool, or null


class CustomModelView(ModelView):
    """Enhanced ModelView with explicit CSV import functionality.

    CSV Import Contract:
    - Empty cells = None/null values
    - Empty strings: Use '""' (literal two quotes)
    - Booleans: "true" or "false" (case-insensitive)
    - Numbers: Plain numeric values (123, 45.67)
    - Strings: Plain text (quotes not needed unless part of the content)
    - Lists/Objects: Valid JSON format (["item1", "item2"], {"key": "value"})
    - Null values: Empty cell or "null"

    Example usage:
    ```python
    class UserImportSchema(BaseModel):
        email: str
        name: str
        is_active: bool = True
        tags: list[str] = []

    class UserAdmin(CustomModelView, model=User):
        can_import = True
        import_schema = UserImportSchema
        import_template_data = {
            "email": "user@example.com",
            "name": "John Doe",
            "is_active": True,
            "tags": ["tag1", "tag2"],
        }
    ```
    """

    form_converter = CustomFormConverter

    column_type_formatters: ClassVar[dict[type, Callable[[Any], Any]]] = {
        bool: bool_formatter,
        type(None): lambda _: "[NONE]",
        str: lambda value: value if value else "[EMPTY STRING]",
    }

    # Import configuration
    can_import: ClassVar[bool] = False
    import_max_rows: ClassVar[int] = 100000
    import_schema: type[BaseModel] | None = None
    import_template_data: ClassVar[dict[str, Any]] = {}
    session_maker: async_sessionmaker[AsyncSession]

    async def to_orm_model(self, validated_data_list: list[Any]) -> list[Any]:
        """Convert list of Pydantic models to list of ORM models."""
        return [self.model(**data.model_dump()) for data in validated_data_list]

    def is_file_upload_schema(self) -> bool:
        """Check if the import schema contains UploadFile fields."""
        if not self.import_schema:
            return False

        for field_info in self.import_schema.model_fields.values():
            annotation = field_info.annotation
            if annotation is None:
                continue

            # Check for UploadFile type (direct or in Union/Optional)
            annotation_str = str(annotation)
            if "UploadFile" in annotation_str or "fastapi.UploadFile" in annotation_str:
                return True

            # Check for list of UploadFile
            if hasattr(annotation, "__origin__") and annotation.__origin__ is list:
                args = getattr(annotation, "__args__", ())
                if args and "UploadFile" in str(args[0]):
                    return True

        return False

    async def import_file_data(
        self, validated_data_list: list[Any], dry_run: bool = False
    ) -> ImportResult:
        """Import file data using validated schema objects."""
        result = ImportResult(
            total_rows=len(validated_data_list),
            successful_rows=0,
            failed_rows=0,
            errors=[],
        )

        if not dry_run:
            try:
                orm_instances = await self.to_orm_model(validated_data_list)
                async with self.session_maker() as session, session.begin():
                    session.add_all(orm_instances)
                    await session.flush()
                    await resync_autoincrement(
                        session, self.model
                    )  # needed to make sure everything works even if custom ids
                    # are imported
                result.successful_rows = len(validated_data_list)
            except Exception as e:
                result.failed_rows = len(validated_data_list)
                result.errors.append(
                    {
                        "row": "batch",
                        "field": "transformation",
                        "message": f"Batch transformation failed: {e!s}",
                        "input_value": "validated_data",
                        "expected_type": "ORM instances",
                        "data": [
                            (
                                data.model_dump()
                                if hasattr(data, "model_dump")
                                else str(data)
                            )
                            for data in validated_data_list
                        ],
                    }
                )
        else:
            # For dry run, just validate that conversion works
            try:
                await self.to_orm_model(validated_data_list)
                result.successful_rows = len(validated_data_list)
            except Exception as e:
                result.failed_rows = len(validated_data_list)
                result.errors.append(
                    {
                        "row": "batch",
                        "field": "validation",
                        "message": f"Validation failed: {e!s}",
                        "input_value": "validated_data",
                        "expected_type": "ORM instances",
                        "data": [
                            (
                                data.model_dump()
                                if hasattr(data, "model_dump")
                                else str(data)
                            )
                            for data in validated_data_list
                        ],
                    }
                )

        return result

    async def import_data(
        self, rows: list[dict[str, Any]], dry_run: bool = False
    ) -> ImportResult:
        """Import CSV data using Pydantic schema with explicit type handling."""
        if not self.import_schema:
            raise CSVImportError("No import schema configured for this model")

        result = ImportResult(
            total_rows=len(rows),
            successful_rows=0,
            failed_rows=0,
            errors=[],
        )

        # Step 1: Validate all rows
        validated_data_list: list[BaseModel] = []
        for row_idx, raw_row in enumerate(rows, 1):
            try:
                # Parse each field value with explicit type handling
                cleaned_row: dict[str, Any] = {}
                for key, value in raw_row.items():
                    if isinstance(value, str):
                        cleaned_row[key] = parse_field_value(value)
                    else:
                        cleaned_row[key] = value

                # Validate with Pydantic schema
                validated_data = self.import_schema.model_validate(cleaned_row)
                validated_data_list.append(validated_data)
                result.successful_rows += 1

            except ValidationError as e:
                result.failed_rows += 1
                for error in e.errors():
                    field_name = str(error["loc"][0]) if error["loc"] else "unknown"
                    result.errors.append(
                        {
                            "row": row_idx,
                            "field": field_name,
                            "message": error["msg"],
                            "input_value": raw_row.get(field_name, "N/A"),
                            "expected_type": self._get_field_type_hint(field_name),
                            "data": raw_row,
                        }
                    )
            except Exception as e:
                result.failed_rows += 1
                result.errors.append(
                    {
                        "row": row_idx,
                        "field": "general",
                        "message": str(e),
                        "input_value": str(raw_row),
                        "expected_type": "N/A",
                        "data": raw_row,
                    }
                )

        # Step 2: Transform and persist if not dry run
        if validated_data_list and not dry_run:
            try:
                orm_instances = await self.to_orm_model(validated_data_list)
                async with self.session_maker() as session, session.begin():
                    session.add_all(orm_instances)
                    await session.flush()
                    await resync_autoincrement(
                        session, self.model
                    )  # needed to make sure everything works even if custom ids
                    # are imported
            except Exception as e:
                result.failed_rows += result.successful_rows
                result.successful_rows = 0
                result.errors.append(
                    {
                        "row": "batch",
                        "field": "transformation",
                        "message": f"Batch transformation failed: {e!s}",
                        "input_value": "all_validated_rows",
                        "expected_type": "ORM instances",
                        "data": [data.model_dump() for data in validated_data_list],
                    }
                )

        logger.warning(f"Import result: {result.model_dump_json(indent=4)[:1000]}")

        return result

    def _get_field_type_hint(self, field_name: str) -> str:
        """Get human-readable type hint for a field."""
        if not self.import_schema or field_name not in self.import_schema.model_fields:
            return "unknown"

        field_info = self.import_schema.model_fields[field_name]
        return str(field_info.annotation)

    def generate_import_template(self) -> str:
        """Generate CSV template with properly serialized sample data."""
        if not self.import_schema:
            raise CSVImportError("No import schema configured for this model")

        if not self.import_template_data:
            raise CSVImportError("No import template data configured for this model")

        headers = list(self.import_schema.model_fields.keys())

        # Generate sample row with consistent serialization
        sample_row: list[str] = []
        try:
            for field_name in headers:
                if field_name in self.import_template_data:
                    value = self.import_template_data[field_name]
                    sample_row.append(serialize_for_csv(value))
                else:
                    # Provide empty string for missing optional fields
                    sample_row.append("")
        except Exception as e:
            raise CSVImportError(f"Error generating template: {e!s}") from e

        # Create CSV with header and sample row
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerow(sample_row)

        return output.getvalue()

    def get_import_format_guide(self) -> dict[str, str]:
        """Generate format guide for CSV imports."""
        if not self.import_schema:
            return {}

        guide = {
            "Empty string vs None": "Use '\"\"' for empty string, "
            "leave cell empty for None/null"
        }

        for field_name, field_info in self.import_schema.model_fields.items():
            annotation = field_info.annotation
            if annotation is None:
                continue

            if annotation is bool:
                guide[field_name] = "Boolean: 'true' or 'false'"
            elif annotation in (int, float):
                guide[field_name] = (
                    f"{annotation.__name__.title()}: numeric value (e.g., 123, 45.67)"
                )
            elif annotation is str:
                guide[field_name] = "String: plain text"
            elif hasattr(annotation, "__origin__") and annotation.__origin__ is list:
                guide[field_name] = 'List: JSON array format (e.g., ["item1", "item2"])'
            elif hasattr(annotation, "__origin__") and annotation.__origin__ is dict:
                guide[field_name] = (
                    'Object: JSON object format (e.g., {"key": "value"})'
                )
            else:
                guide[field_name] = f"Type: {annotation!s}"

        return guide
