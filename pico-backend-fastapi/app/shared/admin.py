import copy
import json
import logging
import re
from collections.abc import AsyncGenerator, Callable
from typing import Any, ClassVar, TypeVar, cast

from fastapi import HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from markupsafe import Markup
from pydantic import BaseModel, ValidationError
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import (
    DeclarativeBase,
    InstrumentedAttribute,
)
from starlette.datastructures import UploadFile
from starlette.responses import StreamingResponse
from wtforms import StringField

from app.base import Base, resync_autoincrement
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

STREAM_EXPORT_BUFFER_SIZE = 1000

logger = logging.getLogger(__name__)


def bool_formatter(value: bool) -> Markup:
    """Return check icon if value is `True` or X otherwise."""
    icon_class = "fa-check text-success" if value else "fa-times text-danger"
    return Markup(f"<i class='fa {icon_class}'></i>")


class ImportResult(BaseModel):
    """Import outcome with validation errors, independent of file format."""

    total_rows: int
    successful_rows: int
    failed_rows: int
    errors: list[dict[str, Any]]


class ImportErrorHTTP(Exception):
    """Raised when import preconditions are not met."""

    pass


class AdminWithImport(SQLAdminAdmin):
    def _find_custom_model_view(self, identity: str) -> "CustomModelView":
        for view in self.views:
            if isinstance(view, CustomModelView) and view.identity == identity:
                return view
        raise HTTPException(status_code=404)

    async def import_jsonl(self, request: Request) -> HTMLResponse:
        """Import endpoint: shows form (GET) and processes upload (POST)."""
        model_view = self._find_custom_model_view(request.path_params["identity"])

        if not model_view.can_import or not model_view.is_accessible(request):
            raise HTTPException(status_code=403)

        if not model_view.import_schema:
            raise ImportErrorHTTP("No import schema configured for this model")

        headers = list(model_view.import_schema.model_fields.keys())

        if request.method == "GET":
            context: dict[str, Any] = {
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

        if request.method == "POST":
            return await self._handle_import_upload(request, model_view)

        raise HTTPException(status_code=405, detail="Method not allowed")

    async def import_template(self, request: Request) -> Response:
        """Download JSON Lines template."""
        model_view = self._find_custom_model_view(request.path_params["identity"])

        if not model_view.can_import or not model_view.is_accessible(request):
            raise HTTPException(status_code=403)

        jsonl_content = model_view.generate_import_template_jsonl()

        filename = f"{model_view.model.__name__.lower()}_import_template.jsonl"

        return Response(
            content=jsonl_content,
            media_type="application/x-ndjson",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    async def _handle_import_upload(
        self,
        request: Request,
        model_view: "CustomModelView",
    ) -> HTMLResponse:
        """Dispatch between file-upload schema and JSONL import."""
        form = await request.form()
        dry_run = form.get("dry_run") == "true"

        if model_view.is_file_upload_schema():
            result = await self._handle_file_upload_import(form, model_view, dry_run)
        else:
            result = await self._handle_jsonl_import(form, model_view, dry_run)

        cleaned: list[dict[str, Any]] = copy.deepcopy(result.errors)
        for error in cleaned:
            data_obj: Any = error.get("data")
            if isinstance(data_obj, list):
                for data in data_obj:
                    if isinstance(data, dict):
                        for key, value in cast("dict[str, Any]", data).items():
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
            elif isinstance(data_obj, dict):
                data_dict = cast("dict[str, Any]", data_obj)
                for key, value in data_dict.items():
                    if isinstance(value, UploadFile):
                        data_dict[key] = f"UploadFile(filename='{value.filename}')"
                    elif isinstance(value, list):
                        data_dict[key] = [
                            (
                                f"UploadFile(filename='{item.filename}')"
                                if isinstance(item, UploadFile)
                                else item
                            )
                            for item in cast("list[Any]", value)
                        ]

        result.errors = cleaned

        context: dict[str, Any] = {
            "model_view": model_view,
            "model_name": model_view.model.__name__,
            "result": result,
            "dry_run": dry_run,
        }
        return await self.templates.TemplateResponse(
            request, "sqladmin/import_result.html", context
        )

    async def _handle_jsonl_import(
        self, form: Any, model_view: "CustomModelView", dry_run: bool
    ) -> "ImportResult":
        """Parse uploaded JSON Lines file and pass rows for validation."""
        file = form.get("jsonl_file")

        if not file or not isinstance(file, UploadFile):
            raise HTTPException(status_code=400, detail="No file uploaded")

        if not file.filename or not file.filename.lower().endswith(".jsonl"):
            raise HTTPException(status_code=400, detail="File must be a .jsonl file")

        raw = await file.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail="Invalid file encoding. Please use UTF-8 encoded files.",
            ) from e

        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid JSON on line {line_number}: {e.msg}",
                ) from e
            if not isinstance(obj, dict):
                raise HTTPException(
                    status_code=400,
                    detail=f"Line {line_number} must be a JSON object",
                )
            rows.append(cast("dict[str, Any]", obj))

        if model_view.import_max_rows and len(rows) > model_view.import_max_rows:
            raise HTTPException(status_code=400, detail="Too many rows in file")

        return await model_view.import_data(rows, dry_run=dry_run)

    async def _handle_file_upload_import(
        self, form: Any, model_view: "CustomModelView", dry_run: bool
    ) -> "ImportResult":
        """Validate pydantic schema for forms with UploadFile fields."""
        form_data: dict[str, Any] = {}

        if not model_view.import_schema:
            raise HTTPException(status_code=500, detail="No import schema configured")

        import_schema = model_view.import_schema
        for field_name, field_info in import_schema.model_fields.items():
            ann_str = str(field_info.annotation)

            if "UploadFile" in ann_str and "list" not in ann_str:
                file_value = form.get(field_name)
                form_data[field_name] = (
                    file_value
                    if isinstance(file_value, UploadFile) and file_value.filename
                    else None
                )
            elif "UploadFile" in ann_str and "list" in ann_str:
                file_values = form.getlist(field_name)
                form_data[field_name] = [
                    f for f in file_values if isinstance(f, UploadFile) and f.filename
                ]
            else:
                form_data[field_name] = form.get(field_name)

        try:
            validated = import_schema.model_validate(form_data)
            return await model_view.import_file_data([validated], dry_run=dry_run)
        except ValidationError as e:
            result = ImportResult(
                total_rows=1, successful_rows=0, failed_rows=1, errors=[]
            )
            for err in e.errors():
                field_name = str(err["loc"][0]) if err["loc"] else "unknown"
                field_info = import_schema.model_fields.get(field_name)
                expected = str(field_info.annotation) if field_info else "unknown"
                result.errors.append(
                    {
                        "row": 1,
                        "field": field_name,
                        "message": err["msg"],
                        "input_value": form_data.get(field_name, "N/A"),
                        "expected_type": expected,
                        "data": form_data,
                    }
                )
            return result

    async def export(self, request: Request) -> Response:
        """Extend export to support JSON Lines streaming as 'jsonl'."""
        identity = request.path_params["identity"]
        export_type = request.path_params["export_type"]

        model_view = self._find_custom_model_view(identity)

        if not model_view.can_export or not model_view.is_accessible(request):
            raise HTTPException(status_code=403)
        if export_type not in model_view.export_types:
            raise HTTPException(status_code=404)

        if hasattr(model_view, "stream_export") and export_type == "jsonl":
            return await model_view.stream_export(request, export_type)

        rows = await model_view.get_model_objects(
            request=request, limit=model_view.export_max_rows
        )
        return await model_view.export_data(rows, export_type=export_type)


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
    @converts("geoalchemy2.types.Geography")  # pyright: ignore[reportUnknownVariableType]
    def conv_location(
        self,
        _model: type,
        _prop: Any,
        kwargs: dict[str, Any],
    ) -> LocationField:  # pyright: ignore[reportIncompatibleMethodOverride]
        return LocationField(**kwargs)


def _json_default(value: Any) -> Any:
    """Default JSON serializer used for non-JSON-native types."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return str(value)


class CustomModelView(ModelView):
    """ModelView with JSON Lines import and export support.

    Import expects one JSON object per line. Export with type "jsonl"
    streams one JSON object per line containing the selected export columns.
    """

    form_converter = CustomFormConverter

    column_type_formatters: ClassVar[dict[type, Callable[[Any], Any]]] = {
        bool: bool_formatter,
        type(None): lambda _: "[NONE]",
        str: lambda value: value if value else "[EMPTY STRING]",
    }

    # Import / Export configuration
    can_import: ClassVar[bool] = False
    import_max_rows: ClassVar[int] = 100000
    import_schema: type[BaseModel] | None = None
    import_template_data: ClassVar[dict[str, Any]] = {}
    session_maker: ClassVar[async_sessionmaker[AsyncSession]]

    export_types: ClassVar[list[str]] = ["jsonl", "json"]

    async def to_orm_model(self, validated_data_list: list[Any]) -> list[Any]:
        """Convert schema models to ORM instances."""
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
        """Persist file-based schema objects or validate on dry-run."""
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
        """Validate and import JSON Lines rows using the configured schema."""
        if not self.import_schema:
            raise ImportErrorHTTP("No import schema configured for this model")

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
                validated_data = self.import_schema.model_validate(raw_row)
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

    def generate_import_template_jsonl(self) -> str:
        """Generate a minimal JSON Lines template using sample data."""
        if not self.import_schema:
            raise ImportErrorHTTP("No import schema configured for this model")

        if not self.import_template_data:
            raise ImportErrorHTTP("No import template data configured for this model")

        line = json.dumps(
            self.import_template_data, ensure_ascii=False, default=_json_default
        )
        return line + "\n"

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

    async def stream_export(
        self, request: Request, export_type: str
    ) -> StreamingResponse:
        """Stream export as JSON Lines when export_type == "jsonl"."""

        async def generate_rows() -> AsyncGenerator[str, None]:
            async with self.session_maker() as session:
                stmt: Select[tuple[Base]] = self.list_query(request)
                stmt: Select[tuple[Base]] = self.sort_query(stmt, request)
                stmt = stmt.execution_options(yield_per=STREAM_EXPORT_BUFFER_SIZE)
                result = await session.stream(stmt)

                async for rowobj in result.scalars():
                    rowdict = {k: getattr(rowobj, k) for k in self._export_prop_names}
                    yield (
                        json.dumps(
                            rowdict,
                            ensure_ascii=False,
                            default=_json_default,
                        )
                        + "\n"
                    )

        filename = self.get_export_name(export_type=export_type)
        return StreamingResponse(
            content=generate_rows(),
            media_type="application/x-ndjson; charset=utf-8",
            headers={"Content-Disposition": f"attachment;filename={filename}"},
        )
