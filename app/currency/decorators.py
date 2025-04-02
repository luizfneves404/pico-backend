import inspect
import logging
from functools import wraps
from typing import Any, Callable, TypeVar, cast

from sqlalchemy import select

from app.currency.currency_service import handle_currency_transaction
from app.currency.models import CurrencyAction, CurrencyType
from app.essays.models import Essay
from app.quiz.models import Challenge, Duel, Quiz

logger = logging.getLogger(__name__)

T = TypeVar("T")


def currency_transaction(action: CurrencyAction, transaction_type: CurrencyType):
    """
    Decorator to handle currency transactions for various actions such as quiz creation, participation, etc.

    Args:
        action (CurrencyAction): The specific action being performed (e.g., QUIZ_CREATION, QUIZ_PARTICIPATION).
        transaction_type (CurrencyType): The type of transaction (e.g., REWARD, DEDUCTION).

    Returns:
        Callable: The decorator function.

    Assumptions:
        - The decorated function must be async
        - The decorated function must have a 'user' parameter and a 'db_session' parameter
        - The decorated function must return an object with an 'id' attribute or a dict with an 'id' key
        - The returned object's ID must correspond to a model instance matching the action's context
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Inspect the function's signature to bind the arguments
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            # Attempt to retrieve 'user' and 'db_session' from the arguments
            user = bound_args.arguments.get("user")
            db_session = bound_args.arguments.get("db_session")

            if user is None:
                raise ValueError("The decorated function must have a 'user' argument.")
            if db_session is None:
                raise ValueError(
                    "The decorated function must have a 'db_session' argument."
                )

            # Execute the original function
            prepared_obj = await func(*args, **kwargs)

            # Retrieve object_id from the returned object
            object_id = getattr(prepared_obj, "id", None)
            if object_id is None and isinstance(prepared_obj, dict):
                object_id = prepared_obj.get("id")

            if object_id is None:
                logger.warning(
                    f"No object ID found for action '{action}'. "
                    f"Proceeding with transaction without a related_object."
                )
                db_obj = None
            else:
                # Map actions to their respective models
                model_map = {
                    # Quiz related actions
                    CurrencyAction.CUSTOM_QUIZ_CREATION: Quiz,
                    CurrencyAction.CUSTOM_QUIZ_JOIN: Quiz,
                    CurrencyAction.QUIZ_CREATION: Quiz,
                    CurrencyAction.QUIZ_JOIN: Quiz,
                    # Duel related actions
                    CurrencyAction.CUSTOM_DUEL_CREATION: Duel,
                    CurrencyAction.CUSTOM_DUEL_JOIN: Duel,
                    CurrencyAction.DUEL_CREATION: Duel,
                    CurrencyAction.DUEL_JOIN: Duel,
                    # Essay related actions
                    CurrencyAction.ESSAY_CREATION: Essay,
                    # Challenge related actions
                    CurrencyAction.CUSTOM_CHALLENGE_CREATION: Challenge,
                    CurrencyAction.CUSTOM_CHALLENGE_JOIN: Challenge,
                    CurrencyAction.CHALLENGE_CREATION: Challenge,
                    CurrencyAction.CHALLENGE_JOIN: Challenge,
                    CurrencyAction.CHALLENGE_COMMISSION: Challenge,
                }

                model = model_map.get(action)

                if not model:
                    logger.error(f"Invalid currency action '{action}'.")
                    raise ValueError(f"Unsupported currency action: {action}")

                result = await db_session.execute(
                    select(model).where(model.id == object_id)
                )
                db_obj = result.scalar_one_or_none()

            # Proceed with the currency transaction
            await handle_currency_transaction(
                db_session=db_session,
                user=user,
                action=action,
                transaction_type=transaction_type,
                related_object=db_obj,  # will be None if object_id wasn't found
            )

            # If the action is CHALLENGE_JOIN, process also the CHALLENGE_COMMISSION transaction for the challenge creator
            if action == CurrencyAction.CHALLENGE_JOIN and db_obj is not None:
                # Uses the created_by field to identify who created the challenge
                creator = getattr(db_obj, "created_by", None)
                if (
                    creator is not None and creator.id != user.id
                ):  # Avoid rewarding the creator if they join their own challenge
                    await handle_currency_transaction(
                        db_session=db_session,
                        user=creator,
                        action=CurrencyAction.CHALLENGE_COMMISSION,
                        transaction_type=CurrencyType.REWARD,  # Always reward for the creator
                        related_object=db_obj,
                    )
                    logger.info(
                        f"Challenge creator (user id: {creator.id}) rewarded for challenge {object_id}"
                    )
                else:
                    logger.warning(
                        f"Challenge creator not found or is the same as participant (user id: {user.id}); "
                        "skipping CHALLENGE_COMMISSION transaction."
                    )

            return prepared_obj

        return cast(Callable[..., T], wrapper)

    return decorator
