from app.countries.models import Country
from app.shared.admin import Admin


class CountryAdmin(Admin, model=Country):
    icon = "fa-solid fa-flag"

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
