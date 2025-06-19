import csv
import io
import re
from dataclasses import dataclass
from typing import Any, Callable, ClassVar, TypeVar

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

from app.shared.bootstrap_sqladmin import monkey_patch_sqladmin

monkey_patch_sqladmin()  # needs to run this before importing sqladmin. add sqladmin imports below!!!
from sqladmin import ModelView
from sqladmin.application import Admin as SQLAdminAdmin
from sqladmin.forms import ModelConverter, converts

MODEL_ATTR = str | InstrumentedAttribute[Any]
ModelType = TypeVar("ModelType", bound=DeclarativeBase)

WKT_RE = re.compile(r"^POINT\(\s*([-0-9\.]+)\s+([-0-9\.]+)\s*\)$")


def bool_formatter(value: bool) -> Markup:
    """Return check icon if value is `True` or X otherwise."""
    icon_class = "fa-check text-success" if value else "fa-times text-danger"
    return Markup(f"<i class='fa {icon_class}'></i>")


@dataclass
class ImportResult:
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
        file = form.get("csv_file")
        dry_run = form.get("dry_run") == "true"

        if not file or not isinstance(file, UploadFile):
            raise HTTPException(status_code=400, detail="No file uploaded")

        if not file.filename or not file.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="File must be a CSV file")

        file_content = await file.read()
        try:
            content = file_content.decode("utf-8")
            csv_reader = csv.DictReader(io.StringIO(content))
            rows = list(csv_reader)

        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid file encoding. Please use UTF-8 encoded CSV files.",
            )
        except csv.Error as e:
            raise HTTPException(
                status_code=400, detail=f"Error parsing CSV file: {str(e)}"
            )

        result = await model_view.import_data(rows, dry_run=dry_run)

        context = {
            "model_view": model_view,
            "model_name": model_view.model.__name__,
            "result": result,
            "dry_run": dry_run,
        }

        return await self.templates.TemplateResponse(
            request, "sqladmin/import_result.html", context
        )


class LocationField(StringField):
    """
    Renders as a text box containing e.g. "POINT(-46.633  -23.550)"
    but you can customize the widget to render two floats if you like.
    """

    def process_formdata(self, valuelist):
        # valuelist is a single‑item list: [ "POINT(lon lat)" ]
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
        model: type,
        prop: ColumnProperty[Geography],
        kwargs: dict[str, Any],
    ) -> LocationField:
        return LocationField(**kwargs)


class CustomModelView(ModelView):
    """Enhanced ModelView with simple CSV import functionality.

    Basic usage:
    ```python
    from pydantic import BaseModel
    from app.shared.admin import CustomModelView

    class UserImportSchema(BaseModel):
        email: str
        name: str

    class UserAdmin(CustomModelView, model=User):
        can_import = True
        import_schema = UserImportSchema
        import_template_data = {
            "email": "user@example.com",
            "name": "John Doe",
        }
        def to_orm_model(self, validated_data: UserImportSchema) -> User:
            return User(
                email=validated_data.email,
                name=validated_data.name,
            )
    ```
    """

    form_converter = CustomFormConverter

    column_type_formatters: ClassVar[dict[type, Callable[[Any], Any]]] = {
        bool: bool_formatter,
        type(None): lambda value: "[NONE]",
        str: lambda value: value if value else "[EMPTY STRING]",
    }

    form_widget_args = {
        "created_at": {
            "readonly": True,
        },
        "updated_at": {
            "readonly": True,
        },
    }

    # Import configuration
    can_import: ClassVar[bool] = False
    """Permission for importing data from CSV."""

    import_max_rows: ClassVar[int] = 100000
    """Maximum number of rows allowed for import."""

    import_schema: type[BaseModel] | None = None

    import_template_data: ClassVar[dict[str, Any]] = {}

    session_maker: async_sessionmaker[AsyncSession]

    async def to_orm_model(self, validated_data: Any) -> Any:
        """Convert Pydantic model to ORM model."""
        return self.model(**validated_data.model_dump())

    async def import_data(
        self, rows: list[dict[str, Any]], dry_run: bool = False
    ) -> ImportResult:
        """Import CSV data using Pydantic schema."""
        if not self.import_schema:
            raise CSVImportError("No import schema configured for this model")

        result = ImportResult(
            total_rows=len(rows),
            successful_rows=0,
            failed_rows=0,
            errors=[],
        )

        async with self.session_maker() as session:
            for row_idx, raw_row in enumerate(rows, 1):
                try:
                    # Clean empty strings to None for optional fields
                    cleaned_row = {
                        k: (v if v != "" else None) for k, v in raw_row.items()
                    }

                    # Validate with Pydantic schema
                    validated_data = self.import_schema.model_validate(cleaned_row)

                    orm_instance = await self.to_orm_model(validated_data)

                    if not dry_run:
                        session.add(orm_instance)

                    result.successful_rows += 1

                except ValidationError as e:
                    result.failed_rows += 1
                    for error in e.errors():
                        field_name = error["loc"][0] if error["loc"] else "unknown"
                        result.errors.append(
                            {
                                "row": row_idx,
                                "field": field_name,
                                "message": error["msg"],
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
                            "data": raw_row,
                        }
                    )

            if not dry_run and result.successful_rows > 0:
                await session.commit()

        return result

    def generate_import_template(self) -> str:
        """Generate CSV template with sample data."""
        if not self.import_schema:
            raise CSVImportError("No import schema configured for this model")

        headers = list(self.import_schema.model_fields.keys())

        # Generate sample row
        if self.import_template_data:
            sample_row = [
                self.import_template_data.get(field_name, "") for field_name in headers
            ]
        else:
            sample_row: list[str] = []
            for field_name, field_info in self.import_schema.model_fields.items():
                sample_value = self._get_sample_value(field_name, field_info)
                sample_row.append(str(sample_value))

        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerow(sample_row)
        return output.getvalue()

    def _get_sample_value(self, field_name: str, field_info: Any) -> str:
        """Generate sample value for CSV template."""
        # Override this method in subclasses for custom sample data
        if hasattr(field_info, "annotation"):
            annotation = getattr(
                field_info.annotation, "__origin__", field_info.annotation
            )
            if annotation is str:
                return f"sample_{field_name}"
            elif annotation is int:
                return "1"
            elif annotation is float:
                return "1.0"
            elif annotation is bool:
                return "true"
        return "sample_value"
