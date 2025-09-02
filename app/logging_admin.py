import logging
import re
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqladmin import BaseView, expose


class LoggingControlView(BaseView):
    """Admin view for displaying the enhanced logging control page.

    Args:
        request: The incoming HTTP request.

    Returns:
        The rendered logging control page with all available logging levels.
    """

    name = "Logging Control"
    icon = "fa-solid fa-gear"
    include_in_schema = False

    @expose("/logging", methods=["GET"])
    async def logging_control_page(self, request: Request) -> Any:
        logging_levels = [
            {
                "name": "CRITICAL",
                "value": logging.CRITICAL,
                "description": "Serious error, program may be unable to continue",
            },
            {
                "name": "ERROR",
                "value": logging.ERROR,
                "description": "A serious problem has occurred",
            },
            {
                "name": "WARNING",
                "value": logging.WARNING,
                "description": "Something unexpected happened",
            },
            {
                "name": "INFO",
                "value": logging.INFO,
                "description": "General information about program execution",
            },
            {
                "name": "DEBUG",
                "value": logging.DEBUG,
                "description": "Detailed information for debugging",
            },
            {
                "name": "NOTSET",
                "value": logging.NOTSET,
                "description": "No level set (inherits from parent)",
            },
        ]

        context: dict[str, Any] = {
            "logging_levels": logging_levels,
        }

        return await self.templates.TemplateResponse(  # pyright: ignore[reportUnknownMemberType]
            request,
            "logging_control.html",
            context=context,
        )


class SetLoggerLevelView(BaseView):
    """Admin view for setting any logger's level.

    Args:
        request: The incoming HTTP request containing the form data.

    Returns:
        A JSON response indicating success or failure.

    Raises:
        HTTPException: If the provided level name is invalid.
    """

    name = "Set Logger Level"
    icon = "fa-solid fa-edit"
    identity = "set_logger_level"
    include_in_schema = False

    def is_visible(self, request: Request) -> bool:
        return False

    @expose("/logging/set-logger-level", methods=["POST"])
    async def set_logger_level(self, request: Request) -> JSONResponse:
        form = await request.form()
        logger_name = form.get("logger_name")
        level_name = form.get("level")

        if not isinstance(logger_name, str) or not isinstance(level_name, str):
            raise HTTPException(status_code=400, detail="Invalid logger name or level")

        try:
            # Get or create the logger
            if logger_name.strip() == "" or logger_name == "root":
                logger = logging.getLogger()
                display_name = "root"
            else:
                logger = logging.getLogger(logger_name)
                display_name = logger_name

            # Validate and set the level
            numeric_level = getattr(logging, level_name.upper())
            old_level = logging.getLevelName(logger.level)
            logger.setLevel(numeric_level)

            # Log the change
            root_logger = logging.getLogger()
            root_logger.info(
                f"Logger '{display_name}' level changed from {old_level}"
                f"to {level_name} via admin interface"
            )

            return JSONResponse(
                content={
                    "success": True,
                    "message": f"Logger '{display_name}' level changed "
                    f"from {old_level} to {level_name}",
                }
            )

        except AttributeError as e:
            root_logger = logging.getLogger()
            root_logger.error(f"Invalid logging level: {level_name} - {e!s}")
            raise HTTPException(
                status_code=400, detail=f"Invalid logging level: {level_name}"
            ) from e
        except Exception as e:
            root_logger = logging.getLogger()
            root_logger.error(f"Error setting logger level: {e!s}")
            raise HTTPException(
                status_code=500, detail=f"Error setting logger level: {e!s}"
            ) from e


class GetAllLoggersView(BaseView):
    """Admin API view for retrieving all current loggers and their levels.

    Args:
        request: The incoming HTTP request.

    Returns:
        A JSON response containing logging information for all active loggers.
    """

    name = "Get All Loggers"
    icon = "fa-solid fa-list"
    identity = "get_all_loggers"
    include_in_schema = False

    def is_visible(self, request: Request) -> bool:
        return False

    @expose("/logging/get-all-loggers", methods=["GET"])
    async def get_all_loggers(self, request: Request) -> JSONResponse:
        loggers_info: dict[str, Any] = {}

        # Get all loggers from the logging manager
        logger_dict = logging.Logger.manager.loggerDict

        # Always include root logger
        root_logger = logging.getLogger()
        loggers_info[""] = self._get_logger_info(root_logger, "root")

        # Add all other loggers
        for name, logger_obj in logger_dict.items():
            if isinstance(logger_obj, logging.Logger):
                loggers_info[name] = self._get_logger_info(logger_obj, name)
            else:
                # PlaceHolder objects - loggers that have been referenced but not
                # created
                loggers_info[name] = {
                    "level": "NOTSET",
                    "effective_level": "NOTSET",
                    "handlers_count": 0,
                    "propagate": True,
                    "parent": None,
                    "disabled": False,
                    "is_placeholder": True,
                }

        return JSONResponse(content=loggers_info)

    def _get_logger_info(self, logger: logging.Logger, name: str) -> dict[str, Any]:
        """Get detailed information about a logger."""
        parent_name = None
        if logger.parent and logger.parent.name:
            parent_name = logger.parent.name
        elif logger.parent and not logger.parent.name:
            parent_name = "root"

        return {
            "level": logging.getLevelName(logger.level),
            "effective_level": logging.getLevelName(logger.getEffectiveLevel()),
            "handlers_count": len(logger.handlers),
            "propagate": logger.propagate,
            "parent": parent_name,
            "disabled": logger.disabled,
            "is_placeholder": False,
        }


class PreviewBulkOperationView(BaseView):
    """Admin API view for previewing bulk logging operations.

    Args:
        request: The incoming HTTP request with JSON body.

    Returns:
        A JSON response with the list of loggers that would be affected.
    """

    name = "Preview Bulk Operation"
    icon = "fa-solid fa-eye"
    identity = "preview_bulk_operation"
    include_in_schema = False

    def is_visible(self, request: Request) -> bool:
        return False

    @expose("/logging/preview-bulk-operation", methods=["POST"])
    async def preview_bulk_operation(self, request: Request) -> JSONResponse:
        data = await request.json()
        pattern = data.get("pattern", "")
        level = data.get("level", "")

        if not level:
            raise HTTPException(status_code=400, detail="Level is required")

        # Validate level
        try:
            getattr(logging, level.upper())
        except AttributeError as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid logging level: {level}"
            ) from e

        affected_loggers = self.get_matching_loggers(pattern)

        return JSONResponse(
            content={
                "affected_loggers": affected_loggers,
                "pattern": pattern,
                "level": level,
            }
        )

    def get_matching_loggers(self, pattern: str) -> list[str]:
        """Get list of logger names matching the given pattern."""
        if not pattern:
            # Empty pattern matches all loggers
            pattern = "*"

        # Convert glob pattern to regex
        regex_pattern = pattern.replace("*", ".*").replace("?", ".")
        regex = re.compile(f"^{regex_pattern}$", re.IGNORECASE)

        matching_loggers: list[str] = []
        logger_dict = logging.Logger.manager.loggerDict

        # Check root logger
        if regex.match("root") or regex.match(""):
            matching_loggers.append("")

        # Check all other loggers
        for name in logger_dict:
            if regex.match(name):
                matching_loggers.append(name)

        return sorted(matching_loggers)


class ExecuteBulkOperationView(BaseView):
    """Admin API view for executing bulk logging operations.

    Args:
        request: The incoming HTTP request with JSON body.

    Returns:
        A JSON response indicating the number of loggers updated.
    """

    name = "Execute Bulk Operation"
    icon = "fa-solid fa-magic"
    identity = "execute_bulk_operation"
    include_in_schema = False

    def is_visible(self, request: Request) -> bool:
        return False

    @expose("/logging/execute-bulk-operation", methods=["POST"])
    async def execute_bulk_operation(self, request: Request) -> JSONResponse:
        data = await request.json()
        pattern = data.get("pattern", "")
        level = data.get("level", "")

        if not level:
            raise HTTPException(status_code=400, detail="Level is required")

        # Validate level
        try:
            numeric_level = getattr(logging, level.upper())
        except AttributeError as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid logging level: {level}"
            ) from e

        # Get matching loggers
        preview_view = PreviewBulkOperationView()
        matching_loggers = preview_view.get_matching_loggers(pattern)

        updated_count = 0
        root_logger = logging.getLogger()

        for logger_name in matching_loggers:
            if logger_name == "":
                logger = logging.getLogger()
                display_name = "root"
            else:
                logger = logging.getLogger(logger_name)
                display_name = logger_name

            old_level = logging.getLevelName(logger.level)
            logger.setLevel(numeric_level)
            updated_count += 1

            root_logger.info(
                f"Bulk operation: Logger '{display_name}' level changed "
                f"from {old_level} to {level}"
            )

        root_logger.info(
            f"Bulk operation completed: {updated_count} loggers updated to {level}"
        )

        return JSONResponse(
            content={
                "success": True,
                "updated_count": updated_count,
                "pattern": pattern,
                "level": level,
            }
        )


class ApplyLoggingPresetView(BaseView):
    """Admin API view for applying logging presets.

    Args:
        request: The incoming HTTP request with JSON body.

    Returns:
        A JSON response indicating the number of loggers updated.
    """

    name = "Apply Logging Preset"
    icon = "fa-solid fa-bookmark"
    identity = "apply_logging_preset"
    include_in_schema = False

    def is_visible(self, request: Request) -> bool:
        return False

    @expose("/logging/apply-logging-preset", methods=["POST"])
    async def apply_logging_preset(self, request: Request) -> JSONResponse:
        data = await request.json()
        preset = data.get("preset", "")

        if not preset:
            raise HTTPException(status_code=400, detail="Preset name is required")

        preset_configs = self._get_preset_configuration(preset)
        if not preset_configs:
            raise HTTPException(status_code=400, detail=f"Unknown preset: {preset}")

        updated_count = 0
        root_logger = logging.getLogger()

        for pattern, level in preset_configs.items():
            numeric_level = getattr(logging, level.upper())

            # Get matching loggers for this pattern
            preview_view = PreviewBulkOperationView()
            matching_loggers = preview_view.get_matching_loggers(pattern)

            for logger_name in matching_loggers:
                if logger_name == "":
                    logger = logging.getLogger()
                    display_name = "root"
                else:
                    logger = logging.getLogger(logger_name)
                    display_name = logger_name

                old_level = logging.getLevelName(logger.level)
                logger.setLevel(numeric_level)
                updated_count += 1

                root_logger.info(
                    f"Preset '{preset}': Logger '{display_name}' level changed "
                    f"from {old_level} to {level}"
                )

        root_logger.info(
            f"Logging preset '{preset}' applied: {updated_count} loggers updated"
        )

        return JSONResponse(
            content={
                "success": True,
                "updated_count": updated_count,
                "preset": preset,
            }
        )

    def _get_preset_configuration(self, preset: str) -> dict[str, str]:
        """Get the configuration for a specific preset."""
        presets = {
            "development": {
                "": "INFO",  # root logger
                "app*": "DEBUG",
                "__main__": "DEBUG",
                "sqlalchemy.engine": "INFO",
                "sqlalchemy.pool": "WARNING",
                "sqlalchemy.orm": "WARNING",
                "uvicorn*": "INFO",
                "fastapi*": "INFO",
                "requests*": "WARNING",
                "urllib3*": "WARNING",
            },
            "production": {
                "*": "WARNING"  # Set everything to WARNING or higher
            },
            "debugging": {
                "*": "DEBUG"  # Set everything to DEBUG
            },
            "quiet": {
                "*": "ERROR"  # Set everything to ERROR or higher
            },
        }

        return presets.get(preset, {})
