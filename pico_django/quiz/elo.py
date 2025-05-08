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


def dynamic_k_factor(num_games: int) -> float:
    """Return the appropriate K-factor based on number of games played.

    K-factor decreases as players play more games:
    - First 10 games: K=40 (high volatility for new players)
    - Games 11-30: K=32 (medium volatility)
    - Games 31-100: K=24 (lower volatility)
    - 100+ games: K=16 (lowest volatility for experienced players)
    """
    if num_games < 10:
        return 40
    elif num_games < 30:
        return 32
    elif num_games < 100:
        return 24
    else:
        return 16


def get_elo_scores(
    player_score: float,
    opponent_score: float,
    player_games_played: int,
    opponent_games_played: int,
    result: Result,
) -> EloScores:
    """
    Calculate new Elo scores for a player and opponent based on the match result
    from the player's perspective. The K-factor is dynamically adjusted based
    on the number of games each player has played.
    """
    k_player = dynamic_k_factor(player_games_played)
    k_opponent = dynamic_k_factor(opponent_games_played)

    actual_score_player = {Result.WIN: 1.0, Result.DRAW: 0.5, Result.LOSE: 0.0}[result]

    expected_score_player = 1 / (1 + 10 ** ((opponent_score - player_score) / 400))

    new_player_score = player_score + k_player * (
        actual_score_player - expected_score_player
    )

    actual_score_opponent = 1.0 - actual_score_player
    expected_score_opponent = 1.0 - expected_score_player

    new_opponent_score = opponent_score + k_opponent * (
        actual_score_opponent - expected_score_opponent
    )

    logger.info(
        f"Calculated new Elo scores - Player: {player_score:.1f}->{new_player_score:.1f} "
        f"(k={k_player}, games={player_games_played}), "
        f"Opponent: {opponent_score:.1f}->{new_opponent_score:.1f} "
        f"(k={k_opponent}, games={opponent_games_played}), Result: {result.value}"
    )

    return EloScores(new_player_score, new_opponent_score)
