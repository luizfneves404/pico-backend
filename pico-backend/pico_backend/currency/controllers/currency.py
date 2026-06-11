import currency.currency_service as currency_service
from asgiref.sync import sync_to_async
from currency.models import Currency
from currency.schemas.currency import (
    DefaultCurrencyIn,
    DefaultCurrencyOut,
    TransactionIn,
    TransactionOut,
)
from ninja import Router
from ninja.errors import HttpError

router = Router()


@router.post(
    "/transaction",
    response={
        201: TransactionOut,
    },
    url_name="create_transaction",
)
async def create_transaction(request, transaction_in: TransactionIn):
    return await currency_service.create_transaction(
        user=request.auth,
        amount=transaction_in.amount,
        description=transaction_in.description,
    )


@router.post(
    "/default-currency",
    response={
        201: DefaultCurrencyOut,
    },
    url_name="create_default_currency",
)
async def fetch_default_currency(request, default_currency_in: DefaultCurrencyIn):
    try:
        return await sync_to_async(currency_service.fetch_default_currency)(
            action=default_currency_in.action,
            currency_type=default_currency_in.currency_type,
        )
    except Currency.DoesNotExist:
        raise HttpError(404, "Default currency not found")
