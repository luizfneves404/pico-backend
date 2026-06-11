from datetime import datetime

from currency.models import CurrencyAction, CurrencyType
from ninja import Schema


class DefaultCurrencyIn(Schema):
    action: CurrencyAction
    currency_type: CurrencyType


class DefaultCurrencyOut(Schema):
    id: int
    action: CurrencyAction
    currency_type: CurrencyType
    value: int


# Only used to create transactions that don't have a related currency object
class TransactionIn(Schema):
    amount: int
    description: str = ""


class TransactionOut(Schema):
    id: int
    amount: int
    action: CurrencyAction | None = None
    created_at: datetime
    description: str = ""


class UserTransactionsOut(Schema):
    transactions: list[TransactionOut]
