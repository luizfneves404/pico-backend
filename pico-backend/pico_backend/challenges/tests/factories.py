from datetime import timedelta

import factory
from api.tests.factories import UserFactory
from django.utils import timezone
from factory.django import DjangoModelFactory

from challenges.models import (
    Challenge,
    ChallengeParticipation,
    Prize,
    Tournament,
    TournamentParticipation,
    TournamentStatus,
)


class ChallengeFactory(DjangoModelFactory):
    class Meta:
        model = Challenge

    name = factory.Sequence(lambda n: f"Test Challenge {n}")
    description = factory.Sequence(lambda n: f"Test Challenge description {n}")
    start_date = factory.LazyFunction(lambda: timezone.localdate())
    end_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=1))
    scoring_system = "frequency"


class ChallengeParticipationFactory(DjangoModelFactory):
    class Meta:
        model = ChallengeParticipation


class TournamentFactory(DjangoModelFactory):
    class Meta:
        model = Tournament

    name = factory.Sequence(lambda n: f"Test Tournament {n}")
    description = factory.Sequence(lambda n: f"Test Tournament description {n}")
    start_time = factory.LazyFunction(lambda: timezone.localtime())
    end_time = factory.LazyFunction(lambda: timezone.localtime() + timedelta(days=1))
    status = TournamentStatus.ONGOING


class TournamentParticipationFactory(DjangoModelFactory):
    class Meta:
        model = TournamentParticipation

    tournament = factory.SubFactory(TournamentFactory)
    user = factory.SubFactory(UserFactory)


class PrizeFactory(DjangoModelFactory):
    class Meta:
        model = Prize

    tournament = factory.SubFactory(TournamentFactory)
    rank = factory.Sequence(lambda n: n + 1)
    amount = factory.Sequence(lambda n: 1000 - n * 100)
