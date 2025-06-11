import contextvars
from typing import Any, Awaitable, Callable

from fastapi import Request, Response
from sqlalchemy.sql.operators import OperatorType
from sqlalchemy.types import JSON, TypeDecorator

_current_locale: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_locale", default="en"
)


def get_locale() -> str:
    return _current_locale.get()


def set_locale(locale: str) -> None:
    _current_locale.set(locale)


async def locale_dispatch(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    # very simple parsing; you might want a real Accept-Language parser
    header = request.headers.get("accept-language", "")
    if header:
        # take the first listed language tag
        lang = header.split(",")[0].strip()
    else:
        lang = "en"
    set_locale(lang)
    return await call_next(request)


def to_locale_dict(obj: object, default_locale: str) -> dict[str, str]:
    """
    Convert an object to a dictionary of { locale: text }
    """
    if not isinstance(obj, dict):
        raise ValueError("obj must be a dict")
    if default_locale not in obj:
        raise ValueError(f"obj must have a {default_locale} key")
    return {k: v for k, v in obj.items() if isinstance(k, str) and isinstance(v, str)}


class TranslatedString:
    def __init__(
        self,
        translations: dict[str, str],
        default_translation: str,
    ):
        self._translations = translations
        self._default_translation = default_translation

    def __str__(self) -> str:
        loc = get_locale()
        return (
            self._translations.get(loc)
            or self._translations.get(loc.split("-", 1)[0])
            or self._default_translation
        )

    def raw(self) -> dict[str, str]:
        return self._translations

    def __getitem__(self, locale: str) -> str:
        return self._translations.get(locale, self._default_translation)

    def __repr__(self) -> str:
        return f"<TranslatedString {self._translations!r}>"


class TranslatableJSON(TypeDecorator[TranslatedString]):
    """
    Stores a dict of { locale: text } in JSON,
    but when reading returns only the string for the current locale.
    """

    impl = JSON
    cache_ok = True

    def __init__(self, default_locale: str = "en") -> None:
        super().__init__()
        self.default_locale = default_locale

    def process_bind_param(self, value: object, dialect: Any) -> dict[str, str] | None:
        if value is None:
            return None
        # if user just passed a single string, wrap it as the default locale
        if isinstance(value, str):
            return {get_locale(): value}
        # if they passed a dict, assume it's { locale_str: text }
        return to_locale_dict(value, self.default_locale)

    def process_result_value(
        self, value: dict[str, str] | None, dialect: Any
    ) -> TranslatedString | None:
        if not value:
            return None

        locale = get_locale()
        language = locale.split("-", 1)[0]

        # Create a list of preferred locale keys in order of priority
        locale_preferences = [locale, language, self.default_locale]

        # Find the first available translation based on preference
        for loc_key in locale_preferences:
            if loc_key in value:
                return TranslatedString(value, value[loc_key])

        # If no preferred locale is found, fallback to the first value
        fallback_value = next(iter(value.values()), "")
        return TranslatedString(value, fallback_value)

    def coerce_compared_value(self, op: OperatorType | None, value: Any) -> Any:
        return self.impl.coerce_compared_value(op, value)  # type: ignore

    def copy(self, **kw: Any) -> "TranslatableJSON":
        return TranslatableJSON(default_locale=self.default_locale)
