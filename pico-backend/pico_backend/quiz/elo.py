import logging
from enum import Enum
from typing import NamedTuple

logger = logging.getLogger(__name__)


class Result(Enum):
    WIN = "win"
    LOSE = "lose"
    DRAW = "draw"


class EloScores(NamedTuple):
    player_score: float
    opponent_score: float


def get_elo_scores(
    player_score: float, opponent_score: float, result: Result
) -> EloScores:
    """
    Calculate the new Elo scores for a player and opponent based on the result of a game.
    The result is relative to the player's perspective against the opponent.
    """
    return EloScores(player_score + 100, opponent_score - 100)
