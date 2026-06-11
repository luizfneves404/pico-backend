import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.utils import IntegrityError
from shared.code_generation import validate_code_format

from .models import (
    UNIQUE_CONSTRAINT_TOURNAMENT_PARTICIPATION,
    Tournament,
    TournamentParticipation,
)

logger = logging.getLogger(__name__)

User = get_user_model()


class TournamentNotFoundError(Exception):
    pass


class TournamentServiceError(Exception):
    pass


class UserNotInTournamentError(Exception):
    pass


class UserAlreadyInTournamentError(Exception):
    pass


def list_tournaments(user_id: int) -> list[Tournament]:
    logger.debug(f"Listing tournaments for user: {user_id}")
    tournaments = list(Tournament.objects.all())
    logger.info(f"Listed {len(tournaments)} tournaments for user: {user_id}")
    return tournaments


async def alist_tournaments(user_id: int) -> list[Tournament]:
    return await sync_to_async(list_tournaments)(user_id)


def join_tournament_by_code(tournament_code: str, user_id: int):
    logger.info(f"User {user_id} joining tournament with code: {tournament_code}")
    tournament_code = tournament_code.upper()[:5]
    validate_code_format(tournament_code)
    try:
        tournament_id = Tournament.objects.values_list("id", flat=True).get(
            code=tournament_code
        )
    except Tournament.DoesNotExist:
        raise TournamentNotFoundError()
    try:
        TournamentParticipation.objects.create(
            tournament_id=tournament_id,
            user_id=user_id,
        )
    except IntegrityError as e:
        if UNIQUE_CONSTRAINT_TOURNAMENT_PARTICIPATION in str(e):
            raise UserAlreadyInTournamentError from e
        raise e
    logger.info(f"User {user_id} successfully joined tournament: {tournament_id}")
    return prepare_detailed_tournament(tournament_id)


def has_pending_duels(tournament_id: int) -> bool:
    logger.info(f"Checking if tournament {tournament_id} has pending duels")
    sql_query = """
        SELECT EXISTS (
            SELECT 1 
            FROM quiz_session s
            JOIN challenges_tournament t ON s.tournament_id = t.id
            JOIN quiz_turn ct ON ct.id = s.current_turn_id
            JOIN quiz_round r ON r.id = ct.round_id
            WHERE t.id = %s
                AND s.duel_status = 'in_progress'
                AND s.created_at BETWEEN t.start_time AND t.end_time
                AND (
                    SELECT COUNT(*)
                    FROM quiz_sessionparticipation sp
                    WHERE sp.session_id = s.id
                ) = 1
                AND NOT (r._order = 0 AND ct._order = 0)  -- Not first turn of first round
        ) AS has_pending_duels
    """

    with connection.cursor() as cursor:
        cursor.execute(sql_query, [tournament_id])
        result = cursor.fetchone()
        return bool(result[0]) if result else False


def prepare_detailed_tournament(tournament_id: int) -> Tournament:
    """
    This function prepares a detailed tournament for the frontend. Should comply with the schema in challenges/schemas.py
    Raises TournamentNotFoundError if the tournament is not found
    """
    tournament = Tournament.objects.filter(id=tournament_id).first()
    if not tournament:
        raise TournamentNotFoundError()
    sql_query = """
    WITH duel_results AS (
        SELECT 
            d.winner_id,
            sp.user_id AS loser_id
        FROM quiz_session d
        JOIN quiz_sessionparticipation sp 
            ON d.id = sp.session_id AND sp.user_id != d.winner_id
        JOIN challenges_tournament ct 
            ON d.tournament_id = ct.id
        WHERE d.tournament_id = %s
        AND d.created_at BETWEEN ct.start_time AND ct.end_time
        AND d.winner_id IS NOT NULL
    ),
    correct_answers_count AS (
        SELECT 
            squ.user_id,
            COUNT(squ.id) AS total_correct_answers
        FROM quiz_sessionquestionuser squ
        JOIN quiz_sessionquestion sq ON squ.session_question_id = sq.id
        JOIN quiz_session s ON sq.session_id = s.id
        JOIN quiz_choice c ON squ.choice_id = c.id
        JOIN challenges_tournament ct ON s.tournament_id = ct.id
        WHERE s.tournament_id = %s
        AND s.created_at BETWEEN ct.start_time AND ct.end_time
        AND c.is_correct = true
        GROUP BY squ.user_id
    ),
    final_scores AS (
        SELECT
            ctp.user_id,
            u.username,
            10 * COALESCE(w.wins, 0) - 5 * COALESCE(l.losses, 0) AS score,
            COALESCE(ca.total_correct_answers, 0) AS total_correct_answers
        FROM challenges_tournamentparticipation ctp
        JOIN api_user u ON ctp.user_id = u.id
        LEFT JOIN (
            SELECT winner_id, COUNT(*) AS wins
            FROM duel_results
            GROUP BY winner_id
        ) w ON ctp.user_id = w.winner_id
        LEFT JOIN (
            SELECT loser_id, COUNT(*) AS losses
            FROM duel_results
            GROUP BY loser_id
        ) l ON ctp.user_id = l.loser_id
        LEFT JOIN correct_answers_count ca ON ctp.user_id = ca.user_id
        WHERE ctp.tournament_id = %s
    ),
    ranked_scores AS (
        SELECT
            user_id,
            username,
            score,
            total_correct_answers,
            RANK() OVER (ORDER BY score DESC, total_correct_answers DESC, user_id ASC) AS rank
        FROM final_scores
    )
    SELECT 
    rs.user_id, 
    rs.username, 
    rs.score, 
    rs.rank,
    COALESCE(p.amount, 0) AS prize_amount
FROM ranked_scores rs
LEFT JOIN challenges_prize p
    ON rs.rank = p.rank AND p.tournament_id = %s
ORDER BY rs.rank ASC;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql_query, [tournament_id, tournament_id, tournament_id, tournament_id]
        )
        columns = [col[0] for col in cursor.description]
        user_rankings_data = [dict(zip(columns, row)) for row in cursor.fetchall()]

    logger.debug(f"User rankings data fetched for tournament: {tournament_id}")

    participations_sorted = sorted(
        [
            {
                "id": user_info["user_id"],
                "username": user_info["username"],
                "score": user_info["score"],
                "rank": user_info["rank"],
                "prize": user_info["prize_amount"],
            }
            for user_info in user_rankings_data
        ],
        key=lambda x: x["rank"],
    )

    # Attach the sorted participations to the tournament instance
    setattr(tournament, "participations", participations_sorted)

    logger.info(f"Prepared tournament: {tournament_id}")
    return tournament


def get_school_ranking(tournament_id: int) -> list[dict[str, Any]]:
    query = """
    WITH duel_results AS (
        SELECT
            d.winner_id,
            sp.user_id AS loser_id
        FROM quiz_session d
        JOIN quiz_sessionparticipation sp
            ON d.id = sp.session_id AND sp.user_id != d.winner_id
        JOIN challenges_tournament ct
            ON d.tournament_id = ct.id
        WHERE d.tournament_id = %s
          AND d.created_at BETWEEN ct.start_time AND ct.end_time
          AND d.winner_id IS NOT NULL
    ),
    school_wins AS (
        SELECT
            winner.school_id AS school_id,
            COUNT(*) AS wins
        FROM duel_results dr
        JOIN api_user winner ON dr.winner_id = winner.id
        JOIN api_user loser ON dr.loser_id = loser.id
        WHERE winner.school_id IS NOT NULL 
          AND loser.school_id IS NOT NULL
          AND winner.school_id <> loser.school_id
        GROUP BY winner.school_id
    ),
    school_losses AS (
        SELECT
            loser.school_id AS school_id,
            COUNT(*) AS losses
        FROM duel_results dr
        JOIN api_user loser ON dr.loser_id = loser.id
        JOIN api_user winner ON dr.winner_id = winner.id
        WHERE loser.school_id IS NOT NULL 
          AND winner.school_id IS NOT NULL
          AND loser.school_id <> winner.school_id
        GROUP BY loser.school_id
    ),
    school_scores AS (
        SELECT
            s.id AS school_id,
            s.name AS school_name,
            10*COALESCE(sw.wins, 0) - 5*COALESCE(sl.losses, 0) AS score
        FROM api_school s
        -- Only include schools with at least one participating user in the tournament.
        JOIN (
           SELECT DISTINCT u.school_id
           FROM api_user u
           JOIN challenges_tournamentparticipation ctp ON u.id = ctp.user_id
           WHERE ctp.tournament_id = %s
             AND u.school_id IS NOT NULL
        ) part ON s.id = part.school_id
        LEFT JOIN school_wins sw ON s.id = sw.school_id
        LEFT JOIN school_losses sl ON s.id = sl.school_id
    ),
    ranked_schools AS (
        SELECT 
            school_id,
            school_name,
            score,
            RANK() OVER (ORDER BY score DESC, school_id ASC) AS rank
        FROM school_scores
    )
    SELECT school_id, school_name, score, rank
    FROM ranked_schools
    ORDER BY rank ASC;
    """

    with connection.cursor() as cursor:
        # Note: We pass the tournament_id twice: once for the duel_results CTE and once for the participation join.
        cursor.execute(query, [tournament_id, tournament_id])
        rows = cursor.fetchall()

    return [
        {"id": row[0], "name": row[1], "score": row[2], "rank": row[3]} for row in rows
    ]
