from typing import ClassVar

from pydantic import BaseModel

from app.countries.models import Country
from app.shared.admin import CustomModelView


class CountryImportSchema(BaseModel):
    code: str
    name: str
    phone_code: str


class CountryAdmin(CustomModelView[CountryImportSchema, Country], model=Country):
    icon = "fa-solid fa-flag"

    # Enable CSV import
    can_import: ClassVar[bool] = True
    import_schema = CountryImportSchema
    import_template_data = {
        "code": "AA",
        "name": "Arlekia Anamasia",
        "phone_code": "690",
    }

    column_list = [
        Country.id,
        Country.code,
        Country.name,
        Country.phone_code,
        Country.created_at,
    ]
    column_searchable_list = [
        Country.code,
        Country.name,
        Country.phone_code,
    ]
    column_sortable_list = [
        Country.id,
        Country.code,
        Country.name,
        Country.phone_code,
        Country.created_at,
    ]
    column_details_list = [
        Country.id,
        Country.code,
        Country.name,
        Country.phone_code,
        Country.created_at,
    ]

    form_columns = [
        "code",
        "name",
        "phone_code",
    ]

    def to_orm_model(self, validated_data: CountryImportSchema) -> Country:
        return Country(
            code=validated_data.code,
            name=validated_data.name,
            phone_code=validated_data.phone_code,
        )
