import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.currency.models import (
    Currency,
    CurrencyAction,
    CurrencyTransaction,
    CurrencyType,
)
from app.users.models import User

logger = logging.getLogger(__name__)


class InsufficientFundsError(Exception):
    """Raised when a user has insufficient funds for a transaction."""

    pass


async def _process_transaction(
    db_session: AsyncSession,
    user: User,
    amount: int,
    currency: Currency | None = None,
    related_object: Any = None,
    description: str = "",
    floor_to_zero: bool = False,
) -> CurrencyTransaction:
    """
    Core function to process balance changes and create transactions.
    This is the only place where balance is modified and CurrencyTransaction objects are created.

    Args:
        session: The database session
        user: The user whose balance is being modified
        amount: The amount to change (positive for addition, negative for deduction)
        currency: Optional currency object for the transaction
        related_object: Optional related object for the transaction
        description: Optional description for the transaction
        floor_to_zero: If True, balance will be floored to 0 instead of raising an error

    Returns:
        CurrencyTransaction: The created transaction object

    Raises:
        InsufficientFundsError: If user has insufficient funds for a deduction and floor_to_zero is False
    """
    if amount:
        gross_balance = user.balance + amount

        if gross_balance < 0:
            if floor_to_zero:
                user.balance = 0
                logger.info(
                    f"Floored user {user.id} balance to 0 because of insufficient funds"
                )
            else:
                logger.info(
                    f"User {user.id} has insufficient funds. Amount was: {abs(amount)}, Balance had only: {user.balance}"
                )
                raise InsufficientFundsError(
                    f"Saldo insuficiente. Necessário: {abs(amount)}, Disponível: {user.balance}"
                )
        else:
            user.balance = gross_balance

    transaction_obj = CurrencyTransaction(
        user=user,
        currency=currency,
        entity=related_object,
        amount=amount,
        description=description,
    )

    db_session.add(transaction_obj)
    await db_session.flush()

    logger.info(
        f"Created transaction {transaction_obj.id} for user {user.id} with amount {amount}"
    )

    return transaction_obj


async def handle_currency_transaction(
    db_session: AsyncSession,
    user: User,
    action: CurrencyAction,
    transaction_type: CurrencyType,
    related_object: Any = None,
) -> int | None:
    """
    Handle a currency transaction for a user.

    Args:
        session: The database session
        user: The user involved in the transaction
        action: The specific action being performed (quiz creation, participation, etc)
        transaction_type: Whether this is a price (deduction) or reward (addition)
        related_object: Optional related object (session, essay, etc)

    Returns:
        int: The ID of the created transaction (for further reference)

    Raises:
        InsufficientFundsError: If user has insufficient funds for a price transaction
    """
    # Get default currency for this action and type
    result = await db_session.execute(
        select(Currency).where(
            Currency.action == action,
            Currency.currency_type == transaction_type,
            Currency.is_default.is_(True),
        )
    )
    currency = result.scalar_one_or_none()

    if not currency:
        logger.warning(
            f"No default currency found for action {action}. Returning None."
        )
        return None

    # Calculate amount based on transaction type
    amount = 0
    if currency.value != 0:
        amount = (
            currency.value
            if transaction_type == CurrencyType.REWARD
            else -currency.value
        )

    transaction_obj = await _process_transaction(
        db_session=db_session,
        user=user,
        amount=amount,
        currency=currency,
        related_object=related_object,
    )

    return transaction_obj.id


async def create_transaction(
    db_session: AsyncSession,
    user: User,
    amount: int,
    description: str = "",
) -> dict[str, Any]:
    """Create a currency transaction with custom amount."""

    transaction = await _process_transaction(
        db_session=db_session, user=user, amount=amount, description=description
    )

    return {
        "id": transaction.id,
        "amount": amount,
        "action": None,
        "created_at": transaction.created_at,
        "description": description,
    }


async def fetch_default_currency(
    db_session: AsyncSession, action: CurrencyAction, currency_type: CurrencyType
) -> dict[str, Any]:
    """Fetch the default currency for a specific action and type."""

    result = await db_session.execute(
        select(Currency).where(
            Currency.action == action,
            Currency.currency_type == currency_type,
            Currency.is_default.is_(True),
        )
    )
    currency = result.scalar_one()

    return {
        "id": currency.id,
        "action": currency.action,
        "currency_type": currency.currency_type,
        "value": currency.value,
    }
