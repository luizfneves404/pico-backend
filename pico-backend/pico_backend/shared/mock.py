from contextlib import contextmanager
from unittest.mock import patch

import essays.tasks as essays_tasks

from shared import openai_utils


@contextmanager
def mock_external_apis():
    with (
        patch("shared.openai_utils._openai_request", autospec=True) as openai_request,
        patch("shared.openai_utils._aopenai_request", autospec=True) as aopenai_request,
        patch(
            "essays.tasks.call_pen_to_print_api", autospec=True
        ) as mock_call_pen_to_print_api,
        patch(
            "essays.tasks.call_amazon_textract_api", autospec=True
        ) as mock_call_amazon_textract_api,
        patch("essays.tasks.call_tinify", autospec=True) as mock_call_tinify,
    ):
        # Define what the mock should return when called
        openai_request.side_effect = openai_utils.mock_openai_request
        aopenai_request.side_effect = openai_utils.mock_aopenai_request
        mock_call_pen_to_print_api.side_effect = essays_tasks.mock_call_pen_to_print_api
        mock_call_amazon_textract_api.side_effect = (
            essays_tasks.mock_call_amazon_textract_api
        )
        mock_call_tinify.side_effect = essays_tasks.mock_call_tinify

        yield {
            "mock_call_pen_to_print_api": mock_call_pen_to_print_api,
            "mock_call_amazon_textract_api": mock_call_amazon_textract_api,
            "mock_call_tinify": mock_call_tinify,
            "mock_openai_request": openai_request,
            "mock_aopenai_request": aopenai_request,
        }
