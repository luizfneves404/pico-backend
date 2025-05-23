"""
This module contains tasks for the quiz functionality.
Do not let anything depend on this module. The only thing that should depend on this module is the arq worker.
Instead, this module depends on other stuff in this directory.
"""

from typing import Any

# from app.flows.session_service import mark_question_timed_out


async def task_mark_question_timed_out(
    ctx: dict[Any, Any], user_id: int, session_id: int, question_id: int
) -> None:
    # mark_question_timed_out(
    #     user_id,
    #     session_id,
    #     question_id,
    # )
    pass  # Commented out to ignore flow/quiz issues
