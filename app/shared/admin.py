from typing import Any, Callable, ClassVar

from markupsafe import Markup
from sqladmin import ModelView


def bool_formatter(value: bool) -> Markup:
    """Return check icon if value is `True` or X otherwise."""
    icon_class = "fa-check text-success" if value else "fa-times text-danger"
    return Markup(f"<i class='fa {icon_class}'></i>")


class Admin(ModelView):
    column_type_formatters: ClassVar[dict[type, Callable[[Any], Any]]] = {
        bool: bool_formatter,
        type(None): lambda value: "[NONE]",
        str: lambda value: value if value else "[EMPTY STRING]",
    }

    form_excluded_columns = [
        "created_at",
        "updated_at",
    ]
