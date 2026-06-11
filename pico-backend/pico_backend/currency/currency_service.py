import logging

from api.models import User
from asgiref.sync import sync_to_async
from django.db import models, transaction

from currency.models import Currency, CurrencyAction, CurrencyType, Transaction
from currency.schemas.currency import DefaultCurrencyOut, TransactionOut

logger = logging.getLogger(__name__)


class InsufficientFundsError(Exception):
    pass


def _process_transaction(
    user: User,
    amount: int,
    currency: Currency | None = None,
    related_object: models.Model | None = None,
    description: str = "",
    floor_to_zero: bool = False,
) -> Transaction:
    """
    Core function to process balance changes and create transactions.
    This is the only place where balance is modified and Transaction objects are created.

    Args:
        user: The user whose balance is being modified
        amount: The amount to change (positive for addition, negative for deduction)
        currency: Optional currency object for the transaction
        related_object: Optional related object for the transaction
        description: Optional description for the transaction
        floor_to_zero: If True, balance will be floored to 0 instead of raising an error

    Returns:
        Transaction: The created transaction object

    Raises:
        InsufficientFundsError: If user has insufficient funds for a deduction and floor_to_zero is False
    """
    with transaction.atomic():
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
                        f"Saldo insuficiente. Necessário: {abs(amount)}, Disponível: {user.balance - amount}"
                    )
            else:
                user.balance = gross_balance

            user.save()

        transaction_obj = Transaction.objects.create(
            user=user,
            currency=currency,
            related_object=related_object,
            amount=amount,
            description=description,
        )

        logger.info(
            f"Created transaction {transaction_obj.id} for user {user.id} with amount {amount}"
        )

        return transaction_obj


def handle_currency_transaction(
    user: User,
    action: CurrencyAction,
    transaction_type: CurrencyType,
    related_object: models.Model | None = None,
) -> int | None:
    """
    Handle a currency transaction for a user.

    Args:
        user: The user involved in the transaction
        action: The specific action being performed (quiz creation, participation, etc)
        transaction_type: Whether this is a price (deduction) or reward (addition)
        related_object: Optional related object (session, essay, etc)

    Returns:
        int: The ID of the created transaction (for further reference)

    Raises:
        InsufficientFundsError: If user has insufficient funds for a price transaction
        Currency.DoesNotExist: If no default currency exists for the action
        ValidationError: If the transaction is invalid
    """
    try:
        currency: Currency = Currency.get_default(action, transaction_type)
    except Currency.DoesNotExist:
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

    transaction_obj = _process_transaction(
        user=user, amount=amount, currency=currency, related_object=related_object
    )

    return transaction_obj.id


async def create_transaction(
    user: User,
    amount: int,
    description: str = "",
) -> TransactionOut:
    """Create a currency transaction with either predefined currency or custom amount."""

    transaction = await sync_to_async(_process_transaction)(
        user=user, amount=amount, description=description
    )

    return TransactionOut(
        id=transaction.id,
        amount=amount,
        action=None,
        created_at=transaction.timestamp,
        description=description,
    )


def fetch_default_currency(
    action: CurrencyAction, currency_type: CurrencyType
) -> DefaultCurrencyOut:
    currency: Currency = Currency.get_default(action, currency_type)

    return DefaultCurrencyOut(
        id=currency.id,
        action=currency.action,
        currency_type=currency.currency_type,
        value=currency.value,
    )
