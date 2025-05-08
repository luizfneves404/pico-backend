from typing import Any, ItemsView

from django.http import HttpRequest
from django.views.debug import SafeExceptionReporterFilter


class CustomExceptionReporterFilter(SafeExceptionReporterFilter):
    """
    Custom exception reporter filter that hides password-related variables.
    This filter will replace any variable name containing 'password' with stars.
    """

    def get_traceback_frame_variables(
        self, request: HttpRequest, tb_frame: Any
    ) -> ItemsView[Any, Any]:
        """
        Returns the filtered dictionary of local variables for the given traceback frame.
        Any variable name containing 'password' will be replaced with stars.
        """
        variables = super().get_traceback_frame_variables(request, tb_frame)
        filtered_dict = {
            k: "**********" if "password" in k.lower() else v for k, v in variables
        }
        return filtered_dict.items()

    def get_post_parameters(self, request: HttpRequest | None = None) -> dict[Any, Any]:
        """
        Returns the filtered dictionary of POST parameters.
        Any parameter name containing 'password' will be replaced with stars.
        """
        post = super().get_post_parameters(request)
        return {
            k: "**********" if "password" in k.lower() else v for k, v in post.items()
        }

    def is_active(self, request: HttpRequest | None = None) -> bool:
        """
        Returns True to activate the filtering in get_post_parameters() and get_traceback_frame_variables().
        """
        return True  # Always active to ensure passwords are never exposed
