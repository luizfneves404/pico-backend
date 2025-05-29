import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqladmin import BaseView, expose


class LoggingControlView(BaseView):
    """Admin view for displaying the logging control page.

    Args:
        request: The incoming HTTP request.

    Returns:
        The rendered logging control page.
    """

    name = "Logging Control"
    icon = "fa-solid fa-gear"
    include_in_schema = False

    @expose("/logging", methods=["GET"])
    async def logging_control_page(self, request: Request) -> Any:
        sql_logger = logging.getLogger("sqlalchemy.engine")
        current_level_name = logging.getLevelName(sql_logger.level)
        levels = [
            {"name": "DEBUG", "value": logging.DEBUG},
            {"name": "INFO", "value": logging.INFO},
            {"name": "WARNING", "value": logging.WARNING},
            {"name": "ERROR", "value": logging.ERROR},
            {"name": "CRITICAL", "value": logging.CRITICAL},
        ]
        context = {
            "current_sql_level": current_level_name,
            "levels": levels,
            "sql_logger_name": "sqlalchemy.engine",
        }

        return await self.templates.TemplateResponse(
            request,
            "logging_control.html",
            context=context,
        )


class SetSqlLoggingLevelView(BaseView):
    """Admin view for setting the SQL logging level.

    Args:
        request: The incoming HTTP request containing the form data.

    Returns:
        A redirect response to the logging control page.

    Raises:
        HTTPException: If the provided level name is invalid.
    """

    name = "Set SQL Logging Level"
    icon = "fa-solid fa-database"
    identity = "set_sql_logging_level"
    include_in_schema = False

    def is_visible(self, request: Request) -> bool:
        return False

    @expose("/logging/set-sql-level", methods=["POST"])
    async def set_sql_logging_level(self, request: Request) -> RedirectResponse:
        form = await request.form()
        level_name = form.get("level")
        if not isinstance(level_name, str):
            raise HTTPException(status_code=400, detail="Invalid level name")

        if level_name:
            try:
                numeric_level = getattr(logging, level_name.upper())
                sql_logger = logging.getLogger("sqlalchemy.engine")
                sql_logger.setLevel(numeric_level)
                root_logger = logging.getLogger()
                root_logger.info(
                    f"SQL logging level changed to {level_name} via admin interface"
                )
            except AttributeError:
                root_logger = logging.getLogger()
                root_logger.error(f"Invalid logging level: {level_name}")

        return RedirectResponse(
            url=request.url_for("admin:logging_control_page"),
            status_code=302,
        )


class GetCurrentLevelsView(BaseView):
    """Admin API view for retrieving current logging levels.

    Args:
        request: The incoming HTTP request.

    Returns:
        A JSON response containing logging information for common loggers.
    """

    name = "Get Current Logging Levels"
    icon = "fa-solid fa-list"
    identity = "get_current_logging_levels"
    include_in_schema = False

    def is_visible(self, request: Request) -> bool:
        return False

    @expose("/logging/get-current-levels", methods=["GET"])
    async def get_current_levels(self, request: Request) -> JSONResponse:
        loggers_info: dict[str, Any] = {}
        logger_names = [
            "root",
            "sqlalchemy.engine",
            "uvicorn",
            "fastapi",
            "app",
        ]
        for logger_name in logger_names:
            if logger_name == "root":
                logger = logging.getLogger()
            else:
                logger = logging.getLogger(logger_name)
            loggers_info[logger_name] = {
                "level": logging.getLevelName(logger.level),
                "effective_level": logging.getLevelName(logger.getEffectiveLevel()),
                "handlers_count": len(logger.handlers),
                "propagate": logger.propagate,
            }
        return JSONResponse(content=loggers_info)
