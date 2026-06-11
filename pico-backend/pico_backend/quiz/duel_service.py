import json
import logging
from datetime import timedelta
from typing import Any, overload

import api.services.fcm_service as fcm_service
from api.models.user import User
from asgiref.sync import sync_to_async
from challenges.models import Tournament
from currency.currency_service import handle_currency_transaction
from currency.models import CurrencyAction, CurrencyType
from django.db import IntegrityError, connection, models, transaction
from django.utils import timezone

import quiz.elo as elo
import quiz.question_service as question_service
import quiz.session_service as session_service
import quiz.utils as quiz_utils
from pico_backend.amp import track_amplitude_event
from quiz.models import (
    UNIQUE_CONSTRAINT_SESSION_USER_PARTICIPATION,
    Duel,
    DuelStatus,
    DuelTurnPhase,
    QuestionSelectionMethod,
    QuestionType,
    Round,
    SessionParticipation,
    SessionQuestion,
    Turn,
)

logger = logging.getLogger(__name__)


class UserAlreadyInDuel(Exception):
    pass


class DuelIsFull(Exception):
    pass


class DuelNotFound(Exception):
    pass


class TournamentNotActive(Exception):
    pass


class TournamentNotFound(Exception):
    pass


class CannotAddQuestionsToNonQueryOfficialDuel(Exception):
    pass


def list_duels(asking_user_id: int) -> list[dict[str, Any]]:
    duel_ids = list(
        Duel.objects.filter(participants__id=asking_user_id)
        .values_list("id", flat=True)
        .distinct()
    )
    return prepare_duel_outs(duel_ids)


async def acreate_and_prepare_duel(
    user: User,
    to_user_id: int | None,
    n_rounds: int,
    n_questions_per_round: int,
    selection_method: QuestionSelectionMethod,
    question_blocks: list[str],
    topic: str,
    subject: str,
    is_fast: bool,
    tournament_id: int | None,
):
    duel = await sync_to_async(create_duel)(
        user.id,
        to_user_id,
        n_rounds,
        n_questions_per_round,
        is_fast,
        selection_method,
        tournament_id,
    )
    await add_questions_to_duel(
        duel,
        selection_method,
        n_rounds,
        n_questions_per_round,
        is_fast,
        question_blocks,
        topic,
        subject,
    )
    logger.info(
        f"Created duel by user {user.username}, to user {to_user_id}, "
        f"with selection method {selection_method}"
    )

    if selection_method == QuestionSelectionMethod.USER_GENERATED:
        action = CurrencyAction.CUSTOM_DUEL_CREATION
    else:
        action = CurrencyAction.DUEL_CREATION
    await sync_to_async(handle_currency_transaction)(
        user=user,
        action=action,
        transaction_type=CurrencyType.PRICE,
        related_object=duel,
    )

    if to_user_id:
        title = f"{user.username} te desafiou para um duelo!"
        body = "Confirme sua participação para começar."
        await sync_to_async(fcm_service.send_notification)(
            [to_user_id],
            title,
            body,
        )

    return await sync_to_async(prepare_duel_outs)(duel.id)


def create_duel(  # GOAT function for creating a duel
    by_user_id: int,
    to_user_id: int | None,
    n_rounds: int,
    n_questions_per_round: int,
    is_fast: bool,
    selection_method: QuestionSelectionMethod,
    tournament_id: int | None = None,
):
    """Creates a duel, taking care of the participants but not the questions. Creates all of the rounds and turns, to be updated later as the duel progresses.

    Args:
        to_user_id (int | None): the user id of the user to challenge
        n_rounds (int): the number of rounds of the duel
        n_questions_per_round (int): the number of questions per round of the duel
        is_fast (bool): whether the questions are fast mode questions
        selection_method (QuestionSelectionMethod): the selection method of the duel
        tournament_id (int | None, optional): the id of the tournament to add the duel to. Defaults to None.

    Raises:
        TournamentNotActive: the tournament is not active
        UserAlreadyInDuel: the user is already in the duel
        e: other exceptions

    Returns:
        Duel: the created duel
    """
    if tournament_id:
        try:
            tournament = Tournament.objects.values("start_time", "end_time").get(
                id=tournament_id
            )
        except Tournament.DoesNotExist:
            raise TournamentNotFound
        if not (tournament["start_time"] < timezone.now() < tournament["end_time"]):
            raise TournamentNotActive
    with transaction.atomic():
        duel = Duel.objects.create(
            created_by_id=by_user_id,
            selection_method=selection_method,
            n_questions_per_round=n_questions_per_round,
            is_fast=is_fast,
            duel_status=DuelStatus.IN_PROGRESS,
            tournament_id=tournament_id,
        )
        participants = [
            SessionParticipation(
                session_id=duel.id,
                user_id=by_user_id,
                confirmed=True,
            )
        ]

        if to_user_id and to_user_id != by_user_id:
            participants.append(
                SessionParticipation(
                    session_id=duel.id,
                    user_id=to_user_id,
                    confirmed=False,
                )
            )
        SessionParticipation.objects.bulk_create(participants)

        # create rounds and turns, following the pattern:
        # Round 1:
        # Turn 1: User 1. attacking
        # Turn 2: User 2. defending
        # Round 2:
        # Turn 1: User 2. attacking
        # Turn 2: User 1. defending
        # Round 3:
        # Turn 1: User 1. attacking
        # Turn 2: User 2. defending
        rounds = [
            Round(duel=duel, query="", _order=i) for i in range(n_rounds)
        ]  # query is not set since it's only used on the query_official selection method (and in this case, it will be set on the add_questions_to_duel_by_query function)
        Round.objects.bulk_create(rounds)

        # Create turns alternating between users and phases
        turns: list[Turn] = []
        for i, round in enumerate(rounds):
            # First turn of round - attacking user alternates each round
            first_user = by_user_id if i % 2 == 0 else to_user_id
            turns.append(
                Turn(
                    round=round,
                    user_id=first_user,
                    phase=DuelTurnPhase.ATTACK,
                    _order=0,
                )
            )

            # Second turn of round - defending user is opposite of attacker
            second_user = to_user_id if i % 2 == 0 else by_user_id
            turns.append(
                Turn(
                    round=round,
                    user_id=second_user,
                    phase=DuelTurnPhase.DEFENSE,
                    _order=1,
                )
            )

        Turn.objects.bulk_create(turns)

        # start the first turn of the duel
        _start_new_turn(duel.id)

    return duel


async def add_questions_to_duel(
    duel: Duel,
    selection_method: QuestionSelectionMethod,
    n_rounds: int,
    n_questions_per_round: int,
    is_fast: bool,
    question_blocks: list[str],
    topic: str,
    subject: str,
):
    """Add questions to a duel based on the selection method. If it's a query-based duel,
    the questions are not added now, you have to call the add_questions_to_duel_by_query function.

    Args:
        duel (Duel): the duel to add questions to
        selection_method (QuestionSelectionMethod): the selection method of the duel
        n_rounds (int): the number of rounds of the duel
        n_questions_per_round (int): the number of questions per round of the duel
        is_fast (bool): whether the questions are fast mode questions
        question_blocks (list[str], optional): the blocks of questions to add to the duel. Defaults to [].
        topic (str, optional): the topic of the questions to add to the duel. Defaults to "".
        subject (str, optional): the subject of the questions to add to the duel. Defaults to "".
    """
    if selection_method == QuestionSelectionMethod.RANDOM_OFFICIAL:
        questions = await sync_to_async(question_service.get_official_questions)(
            query="",
            n=n_rounds * n_questions_per_round,
            question_type=QuestionType.MULTIPLE_CHOICE,
            is_fast=is_fast,
            excluded_user_id=duel.created_by_id,
        )
        await session_service.aadd_questions_to_session(
            duel.id, [question async for question in questions]
        )
    elif selection_method == QuestionSelectionMethod.USER_GENERATED:
        # n_questions_per_block should be chosen so that the total number of questions is n_rounds * n_questions_per_round
        # rounded up to the nearest integer
        n_questions_per_block = (
            -(-n_rounds * n_questions_per_round // len(question_blocks))
            if len(question_blocks) > 0
            else None
        )

        question_instances = (
            await question_service.get_questions_text_from_blocks_or_topic(
                question_blocks=question_blocks,
                topic=topic,
                n_questions_per_block=n_questions_per_block,
                n_questions_for_topic=n_questions_per_round * n_rounds,
                is_fast=is_fast,
                subject=subject,
            )
        )
        # cut out the extra questions if there are more than n_questions_per_round * n_rounds
        question_instances = question_instances[: n_questions_per_round * n_rounds]
        questions = await sync_to_async(
            question_service.create_questions_from_question_instances
        )(question_instances)

        await session_service.aadd_questions_to_session(duel.id, questions)


def add_questions_to_duel_by_query(
    user_id: int,
    duel_id: int,
    query: str,
    area: str,
    source_filter: str,
    difficulty: str,
    is_fast: bool,
) -> None:
    """Add questions to a duel based on a search query.

    Args:
        duel_id: ID of the duel to add questions to
        query: Search query to find questions
        area: Filter questions by area
        source_filter: Filter questions by source
        difficulty: Filter questions by difficulty level
        is_fast: Whether to use fast mode questions

    Raises:
        CannotAddQuestionsToNonQueryOfficialDuel: If duel selection method is not QUERY_OFFICIAL
        DuelNotFound: If duel with given ID does not exist
    """
    duel_data = (
        Duel.objects.values("selection_method", "n_questions_per_round")
        .filter(id=duel_id)
        .first()
    )
    if not duel_data:
        raise DuelNotFound
    if duel_data["selection_method"] != QuestionSelectionMethod.QUERY_OFFICIAL:
        raise CannotAddQuestionsToNonQueryOfficialDuel

    questions = question_service.get_official_questions(
        query,
        n=duel_data["n_questions_per_round"],
        question_type=QuestionType.MULTIPLE_CHOICE,
        is_fast=is_fast,
        excluded_session_ids=[duel_id],
        excluded_user_id=user_id,
        area=area,
        source_filter=source_filter,
        difficulty=difficulty,
    )

    with transaction.atomic():
        session_service.add_questions_to_session(duel_id, questions)

        # Get total question count to determine which round these questions belong to
        question_count = (
            SessionQuestion.objects.filter(session_id=duel_id).values("id").count()
        )
        # Calculate round index (0-based) by dividing total questions by questions per round
        round_index = (
            question_count - duel_data["n_questions_per_round"]
        ) // duel_data["n_questions_per_round"]

        Round.objects.filter(duel_id=duel_id, _order=round_index).update(query=query)

    logger.info(
        f"Added {duel_data['n_questions_per_round']} questions to duel {duel_id} with query: {query}"
    )


async def get_attack_suggestions(asking_user_id: int):
    """Get some active users (answered a question in the last 30 days) that are not the user itself

    Args:
        asking_user_id (int): the user that is asking for attack suggestions

    Returns:
        list[dict]: a list of dictionaries with the user id and username
    """
    return [
        user
        async for user in (
            User.objects.exclude(id=asking_user_id)
            .annotate(last_answer=models.Max("session_question_user_set__timestamp"))
            .filter(last_answer__gte=timezone.now() - timedelta(days=30))
            .order_by("-last_answer")
            .values("id", "username")
        )
    ]


def join_duel_by_code(user: User, code: str) -> dict[str, Any]:
    """
    Adds a user to duel by its code. It also notifies the other user in the duel if successful.

    Args:
        user_id: The user who is joining the duel
        code: The code of the duel to join

    Returns:
        dict: A dictionary representing the duel out

    Raises:
        UserAlreadyInDuel: If the user is already in the duel
        DuelNotFound: If no duel exists with the given code
        DuelIsFull: If the duel has 2 participants or more
    """
    user_id = user.id
    with transaction.atomic():
        participation_count = SessionParticipation.objects.filter(
            session__code=code, session__session_type="duel"
        ).count()

        if participation_count >= 2:
            logger.warning(
                f"Duel with code {code} has {participation_count} participants"
            )
            raise DuelIsFull

        sql = """
        WITH inserted AS (
            INSERT INTO quiz_sessionparticipation (session_id, user_id, confirmed)
            SELECT id, %s, true 
            FROM quiz_session 
            WHERE code = %s AND session_type = 'duel'
            RETURNING session_id
        ),
        joining_user AS (
            SELECT u.username AS joining_username
            FROM api_user u
            WHERE u.id = %s
        ),
        original_user AS (
            SELECT sp.user_id, sp.session_id
            FROM quiz_sessionparticipation sp
            WHERE sp.session_id = (SELECT session_id FROM inserted)
            AND sp.user_id != %s
        )
        SELECT 
            COALESCE(original_user.user_id, NULL) AS original_user_id, 
            joining_user.joining_username, 
            (SELECT session_id FROM inserted) AS duel_id
        FROM joining_user
        LEFT JOIN original_user ON TRUE;
        """
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    sql,
                    [user_id, code, user_id, user_id],
                )
                result = cursor.fetchone()
            except IntegrityError as e:
                if UNIQUE_CONSTRAINT_SESSION_USER_PARTICIPATION in str(e):
                    raise UserAlreadyInDuel from e
                raise e

        original_user_id, joining_username, duel_id = result

        if not duel_id:
            raise DuelNotFound

        Turn.objects.filter(round__duel_id=duel_id, user_id__isnull=True).update(
            user_id=user_id
        )

        duel = Duel.objects.get(id=duel_id)

        if duel.selection_method == QuestionSelectionMethod.USER_GENERATED:
            action = CurrencyAction.CUSTOM_DUEL_JOIN
        else:
            action = CurrencyAction.DUEL_JOIN
        handle_currency_transaction(
            user=user,
            action=action,
            transaction_type=CurrencyType.PRICE,
            related_object=duel,
        )

    title = "Um novo desafiante apareceu!"
    body = f"{joining_username} entrou no duelo!"
    fcm_service.send_notification(
        original_user_id,
        title,
        body,
    )
    logger.info(f"User {joining_username} joined duel {duel_id} by code {code}")
    return prepare_duel_outs(duel_id)


def join_duel_by_tournament(user_id: int, tournament_id: int) -> dict[str, Any]:
    """
    Joins a duel by tournament id, checking if the duel has exactly one participant and if the user is not already in the duel.
    Performs duel transition (since a participation gets confirmed) and sends notifications.

    Args:
        user_id: The user who is joining the duel
        tournament_id: The id of the tournament to join

    Returns:
        dict: A dictionary representing the duel out

    Raises:
        DuelNotFound: If there is no duel in the tournament with the given id
        UserAlreadyInDuel: If the user is already in the duel
    """
    with transaction.atomic():
        duel = (
            SessionParticipation.objects.filter(
                session__tournament_id=tournament_id, session__duel_status="in_progress"
            )
            .values("session_id")
            .annotate(count=models.Count("id"))
            .filter(count__lte=1)
            .order_by("session_id")
            .first()
        )

        if not duel:
            raise DuelNotFound

        sql = """
            WITH ins AS (
                INSERT INTO quiz_sessionparticipation (session_id, user_id, confirmed)
                SELECT s.id, %s, true
                FROM quiz_session s
                WHERE s.tournament_id = %s
                AND s.duel_status = 'in_progress'
                AND (
                    SELECT COUNT(*) 
                    FROM quiz_sessionparticipation sp 
                    WHERE sp.session_id = s.id
                ) = 1
                LIMIT 1
                RETURNING session_id
            )
            SELECT sp.user_id, u.username AS joining_username, sp.session_id
            FROM quiz_sessionparticipation sp
            JOIN api_user u ON u.id = sp.user_id
            WHERE sp.session_id = (SELECT session_id FROM ins)
            AND sp.user_id <> %s;
        """

        with connection.cursor() as cursor:
            try:
                cursor.execute(sql, [user_id, tournament_id, user_id])
                result = cursor.fetchone()
            except IntegrityError as e:
                if UNIQUE_CONSTRAINT_SESSION_USER_PARTICIPATION in str(e):
                    raise UserAlreadyInDuel from e
                raise e

        original_user_id, joining_username, duel_id = result

        Turn.objects.filter(round__duel_id=duel_id, user_id__isnull=True).update(
            user_id=user_id
        )

    joining_user = User.objects.get(id=user_id)
    username = joining_user.username

    title = "Um novo desafiante apareceu!"
    body = f"{username} entrou no duelo!"
    fcm_service.send_notification(
        [original_user_id],
        title,
        body,
    )
    logger.info(
        f"User {username} joined tournament duel {duel_id} in tournament {tournament_id}"
    )

    return prepare_duel_outs(duel_id)


def invite_to_duel(inviting_user: User, invited_user_id: int, duel_id: int):
    """
    Invites a user to a duel, checking if the duel has exactly one participant and if the user is not already in the duel.
    Does not perform duel transition (since a participation does not get confirmed) and sends notifications.

    Args:
        duel_id: The id of the duel to invite the user to
        inviting_user: The user who is inviting the other user to the duel
        invited_user_id: The id of the user who is being invited to the duel

    Raises:
        DuelIsFull: If the duel already has 2 participants
    """
    with transaction.atomic():
        participation_count = (
            SessionParticipation.objects.filter(session_id=duel_id)
            .select_for_update()
            .count()
        )

        if participation_count >= 2:
            logger.warning(f"Duel {duel_id} already has 2 participants")
            raise DuelIsFull

        SessionParticipation.objects.create(
            session_id=duel_id,
            user_id=invited_user_id,
            confirmed=False,
        )

    logger.info(
        f"User {inviting_user.username} invited user {invited_user_id} to duel {duel_id}"
    )
    title = f"{inviting_user.username} te desafiou para um duelo!"
    body = "Confirme sua participação para começar."
    fcm_service.send_notification(
        [invited_user_id],
        title,
        body,
    )


def confirm_duel_participant(user: User, duel_id: int):
    user_id = user.id
    """
    Confirms a participant in a duel, performing duel transition (since a participation gets confirmed) and sending notifications.

    Args:
        duel_id: The id of the duel to confirm the participant in
        user_id: The id of the user to confirm in the duel
    """
    with transaction.atomic():
        SessionParticipation.objects.filter(
            session_id=duel_id,
            user_id=user_id,
        ).update(confirmed=True)

        Turn.objects.filter(round__duel_id=duel_id, user_id__isnull=True).update(
            user_id=user_id
        )

        duel = Duel.objects.get(id=duel_id)

        if duel.selection_method == QuestionSelectionMethod.USER_GENERATED:
            action = CurrencyAction.CUSTOM_DUEL_JOIN
        else:
            action = CurrencyAction.DUEL_JOIN
        handle_currency_transaction(
            user=user,
            action=action,
            transaction_type=CurrencyType.PRICE,
            related_object=duel,
        )

    logger.info(f"Confirmed participant with user_id {user_id} for duel {duel_id}")


def reject_duel_participant(user_id: int, duel_id: int):
    """
    Rejects a participant in a duel, deleting the participation.

    Args:
        duel_id: The id of the duel to reject the participant in
        user_id: The id of the user to reject in the duel
    """
    SessionParticipation.objects.filter(
        session_id=duel_id,
        user_id=user_id,
    ).delete()
    logger.info(f"Rejected participant with user_id {user_id} for duel {duel_id}")


def mark_question_seen(user_id: int, duel_id: int, question_id: int):
    """
    Marks a question as seen for a user in a duel. It does not transition the duel's state.

    Args:
        user_id: The id of the user to mark the question as seen for
        duel_id: The id of the duel to mark the question as seen in
        question_id: The id of the question to mark as seen
    """
    session_service.mark_question_seen(
        user_id=user_id,
        session_id=duel_id,
        question_id=question_id,
    )


def mark_question_timed_out(user: User, duel_id: int, question_id: int):
    """
    Marks a question as timed out for a user in a duel.
    It transitions the duel's state, and sends notifications.
    You must call mark_question_seen first.

    Args:
        user: The user who timed out
        duel_id: The id of the duel to mark the question as timed out in
        question_id: The id of the question to mark as timed out
    """
    with transaction.atomic():
        session_service.mark_question_timed_out(
            user_id=user.id,
            session_id=duel_id,
            question_id=question_id,
        )

        duel_state = _transition_duel_state(duel_id, user.id)

    _send_duel_notifications(
        duel_state,
        user.id,
        user.username,
        should_start_new_turn=duel_state["should_start_new_turn"],
        is_duel_complete=duel_state["is_duel_complete"],
    )

    logger.info(
        f"Marked question {question_id} as timed out for duel {duel_id}, user {user.id}"
    )


def submit_answer(
    user: User, duel_id: int, question_id: int, answer_choice_id: int
) -> None:
    """
    Submits an answer for a user's question in a duel. It transitions the duel's state,
    sends notifications, and, if the duel is complete, updates scores and notifies the opponent.
    You must call mark_question_seen first.

    Args:
        user: The user who is submitting the answer
        duel_id: The id of the duel to submit the answer in
        question_id: The id of the question to submit the answer for
        answer_choice_id: The id of the choice that the user submitted

    Raises:
        AnswerAlreadySubmitted: If the answer has already been submitted
    """

    with transaction.atomic():
        session_service.submit_answer(
            user_id=user.id,
            session_id=duel_id,
            question_id=question_id,
            answer_choice_id=answer_choice_id,
        )

        duel_state = _transition_duel_state(duel_id, user.id)

    _send_duel_notifications(
        duel_state,
        user.id,
        user.username,
        should_start_new_turn=duel_state["should_start_new_turn"],
        is_duel_complete=duel_state["is_duel_complete"],
    )

    logger.info(
        f"Successfully submitted answer for duel {duel_id}, question {question_id}, "
        f"user {user.id}, choice {answer_choice_id}"
    )


def _transition_duel_state(duel_id: int, user_id: int) -> dict[str, Any]:
    """
    Checks and transitions duel state, and should always be called after an answer submission (including question timeout).
    Handles turn progression and duel completion if necessary.

    Args:
        duel_id: The duel ID
        user_id: The user whose answers will be checked to determine if a new turn should start. If this user has answered all questions of the current turn, a new turn should be started (see implementation to see how this is done).

    Returns:
        Dictionary containing state information for notifications:
        {
            'new_turn_user_id': Optional[int],
            'winner_id': Optional[int],
            'opponent_id': Optional[int],
            'player_stats': Optional[dict],
            'opponent_stats': Optional[dict]
        }
    """
    with transaction.atomic():
        sql = """
        WITH answer_count AS (
            SELECT 
                squ.user_id, 
                COUNT(*) AS total_answers
            FROM quiz_sessionquestionuser AS squ
            INNER JOIN quiz_sessionquestion AS sq 
                ON sq.id = squ.session_question_id
            WHERE sq.session_id = %s
            GROUP BY squ.user_id
        ),
        session_info AS (
            SELECT 
                n_questions_per_round,
                (SELECT COUNT(*) FROM quiz_round WHERE duel_id = %s) AS n_rounds
            FROM quiz_session
            WHERE id = %s
        ),
        current_user_answers AS (
            SELECT 
                %s AS user_id,
                COALESCE(ac.total_answers, 0) as total_answers
            FROM (SELECT 1) dummy
            LEFT JOIN answer_count ac ON ac.user_id = %s
        )
        SELECT
            (
                cu.total_answers > 0 
                AND MOD(cu.total_answers, si.n_questions_per_round) = 0
                AND NOT (
                    cu.total_answers >= si.n_questions_per_round * si.n_rounds
                    AND COALESCE(
                        (SELECT total_answers 
                         FROM answer_count 
                         WHERE user_id != %s
                         LIMIT 1), 0
                    ) >= si.n_questions_per_round * si.n_rounds
                )
            )
            AS should_start_new_turn,
            (
                cu.total_answers >= si.n_questions_per_round * si.n_rounds
                AND COALESCE(
                    (SELECT total_answers 
                     FROM answer_count 
                     WHERE user_id != %s
                     LIMIT 1), 0
                ) >= si.n_questions_per_round * si.n_rounds
            )
            AS is_duel_complete
        FROM current_user_answers cu
        CROSS JOIN session_info si;
        """
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                [
                    duel_id,
                    duel_id,
                    duel_id,
                    user_id,
                    user_id,
                    user_id,
                    user_id,
                ],
            )
            result = cursor.fetchone()
            should_start_new_turn, is_duel_complete = result

        state: dict[str, Any] = {
            "new_turn_user_id": None,
            "winner_id": None,
            "opponent_id": None,
            "player_stats": None,
            "opponent_stats": None,
            "should_start_new_turn": should_start_new_turn,
            "is_duel_complete": is_duel_complete,
        }

        logger.debug(
            f"should_start_new_turn: {should_start_new_turn}, is_duel_complete: {is_duel_complete}"
        )

        if should_start_new_turn:
            state["new_turn_user_id"] = _start_new_turn(duel_id)
            track_amplitude_event(
                user_id,
                "Duel turn finished and new turn started",
                event_properties={
                    "duel_id": duel_id,
                },
            )
        elif is_duel_complete:
            completion_state = _complete_duel(duel_id, user_id)
            state.update(completion_state)

        return state


def _start_new_turn(duel_id: int) -> int:
    """
    Starts a new turn and returns the new turn user ID.
    It updates the current turn to the next turn and sets the start time of that turn to the current time.
    It also handles the case where there is no current turn, and the first turn of the duel is chosen.
    Parameters:
      duel_id: The identifier for the duel whose turn is being advanced.

    Returns:
      The user_id associated with the new turn.

    Raises:
      ValueError: If no new turn can be started.
    """
    now = timezone.now()
    with transaction.atomic():
        # The SQL below handles two cases:
        # 1. If there is no current turn, it picks the first turn
        #    (defined as _order=0 of the round with _order=0 for the duel).
        # 2. If there is a current turn, it picks the next turn,
        #    either in the same round (with higher _order) or, if none,
        #    the first turn (with _order=0) in the next round.
        sql = """
        WITH current_turn AS (
            SELECT t.id, t._order, t.round_id, t.user_id
            FROM quiz_turn t
            INNER JOIN quiz_session s ON s.current_turn_id = t.id
            WHERE s.id = %s
        ),
        next_turn AS (
            SELECT t.id, t.user_id, t.round_id, t._order
            FROM quiz_turn t
            LEFT JOIN current_turn ct ON true
            WHERE (
                -- Case 1: If no current turn exists, choose the first turn in the first round
                ct.id IS NULL 
                AND t._order = 0 
                AND t.round_id = (SELECT id FROM quiz_round WHERE duel_id = %s AND _order = 0)
            )
            OR (
                -- Case 2: If a current turn exists, find the next turn based on round and order
                ct.id IS NOT NULL
                AND (
                    (t.round_id = ct.round_id AND t._order > ct._order)  -- Same round, next order
                    OR (t.round_id > ct.round_id AND t._order = 0)      -- Next round, first turn
                )
            )
        ),
        ordered_turn AS (
            SELECT id, user_id
            FROM next_turn
            ORDER BY round_id, _order
            LIMIT 1
        )
        UPDATE quiz_session s
        SET current_turn_id = ot.id
        FROM ordered_turn ot
        WHERE s.id = %s;

        UPDATE quiz_turn t
        SET start_time = %s
        FROM quiz_session s
        WHERE s.id = %s AND s.current_turn_id = t.id
        RETURNING t.user_id;
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [duel_id, duel_id, duel_id, now, duel_id])
            cursor.nextset()
            result = cursor.fetchone()
            logger.info(f"Started new turn for duel {duel_id}, user {result[0]}")
        return result[0]


def _complete_duel(duel_id: int, user_id: int) -> dict[str, Any]:
    """Completes the duel and returns state info"""
    with transaction.atomic():
        sql = """
        WITH base AS (
        SELECT 
            sp.user_id,
            CASE WHEN sp.user_id = %s THEN 'player' ELSE 'opponent' END AS role,
            ui.duel_score,
            s.duel_status,
            s.id AS session_id
        FROM quiz_sessionparticipation sp
        LEFT JOIN quiz_userinfo ui ON ui.user_id = sp.user_id
        LEFT JOIN quiz_session s ON sp.session_id = s.id
        WHERE sp.session_id = %s
    ),
    answer_stats AS (
        SELECT 
            squ.user_id, 
            COUNT(*) AS total_answers, 
            COUNT(CASE WHEN c.is_correct THEN 1 END) AS correct_answers
        FROM quiz_sessionquestionuser AS squ
        LEFT JOIN quiz_choice AS c ON c.id = squ.choice_id
        INNER JOIN quiz_sessionquestion AS sq ON sq.id = squ.session_question_id
        WHERE sq.session_id = %s
        GROUP BY squ.user_id
    ),
    max_scores AS (
        SELECT 
            MAX(correct_answers) AS max_correct 
        FROM answer_stats
    ),
    top_scorers AS (
        SELECT 
            user_id 
        FROM answer_stats, max_scores 
        WHERE correct_answers = max_correct
    ),
    unique_winner AS (
        SELECT 
            CASE 
                WHEN COUNT(*) = 1 THEN MAX(user_id) 
                ELSE NULL 
            END AS winner
        FROM top_scorers
    ),
    user_stats AS (
        SELECT
            b.user_id,
            json_build_object(
                'duel_score', COALESCE(b.duel_score, 0),
                'completed_duels', COUNT(DISTINCT b.session_id) FILTER (WHERE b.duel_status = 'completed')
            ) AS stats
        FROM base b
        GROUP BY b.user_id, b.duel_score
    )
    UPDATE quiz_session AS s
    SET 
        current_turn_id = NULL,
        duel_status = 'completed',
        winner_id = (SELECT winner FROM unique_winner)
    WHERE s.id = %s
    RETURNING 
        s.winner_id,
        (SELECT user_id FROM base WHERE role = 'opponent' LIMIT 1) AS opponent_id,
        (SELECT stats FROM user_stats WHERE user_id = %s) AS player_stats,
        (SELECT stats FROM user_stats WHERE user_id = (
            SELECT user_id FROM base WHERE role = 'opponent' LIMIT 1
        )) AS opponent_stats;
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [user_id, duel_id, duel_id, duel_id, user_id])
            result = cursor.fetchone()
            winner_id, opponent_id, player_stats, opponent_stats = result

        logger.info(f"Completed duel {duel_id}, user {user_id}")

        # Determine game result
        result = (
            elo.Result.DRAW
            if winner_id is None
            else elo.Result.WIN
            if winner_id == user_id
            else elo.Result.LOSE
        )

        _update_scores(
            duel_id,
            user_id,
            player_stats["duel_score"],
            player_stats["completed_duels"],
            opponent_id,
            opponent_stats["duel_score"],
            opponent_stats["completed_duels"],
            result,
        )

    loser_id = opponent_id if winner_id == user_id else user_id
    track_amplitude_event(
        user_id,
        "Duel completed",
        event_properties={
            "duel_id": duel_id,
            "winner_id": winner_id,
            "loser_id": loser_id,
        },
    )

    return {
        "winner_id": winner_id,
        "opponent_id": opponent_id,
        "player_stats": player_stats,
        "opponent_stats": opponent_stats,
    }


def _send_duel_notifications(
    duel_state: dict[str, Any],
    user_id: int,
    username: str,
    should_start_new_turn: bool,
    is_duel_complete: bool,
) -> None:
    """Sends appropriate notifications based on duel state"""
    if should_start_new_turn:
        new_turn_user_id = duel_state["new_turn_user_id"]
        if new_turn_user_id != user_id:
            title = "É sua vez de responder no duelo!"
            body = f"{username} está te esperando"
            fcm_service.send_notification(
                [new_turn_user_id],
                title,
                body,
            )

    elif is_duel_complete:
        winner_id = duel_state["winner_id"]
        opponent_id = duel_state["opponent_id"]

        if winner_id:
            if winner_id == user_id:
                title = "Você perdeu o duelo!"  # Notification for the opponent
                body = f"Que pena! Você perdeu o duelo contra {username}!"
            else:
                title = "Você venceu o duelo!"
                body = f"Parabéns! Você venceu o duelo contra {username}!"
        else:
            title = "O duelo acabou!"
            body = f"Voce empatou com {username}!"

        fcm_service.send_notification(
            [opponent_id],
            title,
            body,
        )


def _update_scores(
    duel_id: int,
    player_id: int,
    player_score: float,
    player_games_played: int,
    opponent_id: int,
    opponent_score: float,
    opponent_games_played: int,
    result: elo.Result,
):
    logger.info(
        f"Updating scores after completing duel {duel_id}, user {player_id}, opponent {opponent_id}, result {result}"
    )
    new_player_score, new_opponent_score = elo.get_elo_scores(
        player_score, opponent_score, player_games_played, opponent_games_played, result
    )

    sql = """
    WITH user_score_updates AS (
        UPDATE quiz_userinfo
        SET duel_score = CASE
            WHEN user_id = %s THEN %s
            WHEN user_id = %s THEN %s
        END
        WHERE user_id IN (%s, %s)
        RETURNING user_id, duel_score
    )
    UPDATE quiz_sessionparticipation sp
    SET duel_score_change = CASE
        WHEN sp.user_id = %s THEN %s - %s
        WHEN sp.user_id = %s THEN %s - %s
    END
    WHERE sp.user_id IN (%s, %s)
    AND sp.session_id = %s
    RETURNING sp.user_id, sp.duel_score_change;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            [
                player_id,
                new_player_score,
                opponent_id,
                new_opponent_score,
                player_id,
                opponent_id,
                player_id,
                new_player_score,
                player_score,
                opponent_id,
                new_opponent_score,
                opponent_score,
                player_id,
                opponent_id,
                duel_id,
            ],
        )
        logger.info(f"Score changes: {cursor.fetchall()}")


def get_duel_out(duel_id: int):
    return prepare_duel_outs(duel_id)


@overload
def prepare_duel_outs(duel_ids: int) -> dict[str, Any]: ...


@overload
def prepare_duel_outs(duel_ids: list[int]) -> list[dict[str, Any]]: ...


def prepare_duel_outs(
    duel_ids: list[int] | int,
) -> list[dict[str, Any]] | dict[str, Any]:
    """
    Prepares a list of duel data (as dictionaries) for the given duel IDs. Prepared to comply with quiz/schemas/duels.py.

    Args:
        duel_ids (list[int] | int): The list of duel IDs to prepare the data for.

    Returns:
        list[dict[str, Any]] | dict[str, Any]: A list of duel data dictionaries or a single duel data dictionary.
    Raises:
        DuelNotFound: If there is one duel and it is not found
    """
    if isinstance(duel_ids, list) and not duel_ids:
        return []
    ids_list = [duel_ids] if isinstance(duel_ids, int) else duel_ids

    query = """
        WITH question_data AS (
            SELECT 
                sq.session_id,
                jsonb_agg(
                    jsonb_build_object(
                        'id', q.id,
                        'allow_resubmit', q.allow_resubmit,
                        'subject', q.subject,
                        'text', q.text,
                        'answer_text', q.answer_text,
                        'answer_image', '',
                        'image', '',
                        'video_url', '',
                        'source', q.source,
                        'difficulty', q.difficulty,
                        'category', q.category,
                        'subcategory', q.subcategory,
                        'choices', (
                            SELECT COALESCE(jsonb_agg(
                                jsonb_build_object(
                                    'id', c.id,
                                    'text', c.text,
                                    'image', '',
                                    'is_correct', c.is_correct
                                )
                            ), '[]'::jsonb)
                            FROM quiz_choice c
                            WHERE c.question_id = q.id
                        ),
                        'answers', (
                            SELECT COALESCE(jsonb_agg(
                                jsonb_build_object(
                                    'choice_id', squ.choice_id,
                                    'submitted_text', squ.submitted_text,
                                    'feedback', squ.feedback,
                                    'grade', squ.grade,
                                    'timestamp', squ.timestamp,
                                    'user', jsonb_build_object(
                                        'id', u.id,
                                        'username', u.username
                                    ),
                                    'timed_out', squ.timed_out
                                )
                            ), '[]'::jsonb)
                            FROM quiz_sessionquestionuser squ
                            JOIN api_user u ON u.id = squ.user_id
                            WHERE squ.session_question_id = sq.id
                        )
                    )
                    ORDER BY sq.order
                ) AS questions_and_answers
            FROM quiz_sessionquestion sq
            JOIN quiz_question q ON q.id = sq.question_id
            WHERE sq.session_id = ANY(%s)
            GROUP BY sq.session_id
        ),
        participation_data AS (
            SELECT 
                sp.session_id,
                jsonb_agg(
                    jsonb_build_object(
                        'user', jsonb_build_object(
                            'id', u.id,
                            'username', u.username
                        ),
                        'confirmed', sp.confirmed,
                        'duel_score_change', sp.duel_score_change
                    )
                ) AS participations
            FROM quiz_sessionparticipation sp
            JOIN api_user u ON u.id = sp.user_id
            WHERE sp.session_id = ANY(%s)
            GROUP BY sp.session_id
        ),
        round_data AS (
            SELECT
                r.duel_id,
                jsonb_agg(
                    jsonb_build_object(
                        'query', r.query
                    )
                    ORDER BY r._order
                ) AS rounds,
                COUNT(*) AS n_rounds
            FROM quiz_round r
            WHERE r.duel_id = ANY(%s)
            GROUP BY r.duel_id
        ),
        current_turn_data AS (
            SELECT 
                s.id as session_id,
                t.phase as duel_phase,
                t.start_time as current_turn_start_time,
                t.user_id as current_turn_user_id
            FROM quiz_session s
            LEFT JOIN quiz_turn t ON t.id = s.current_turn_id
            WHERE s.id = ANY(%s)
        )
        SELECT COALESCE(jsonb_agg(
            jsonb_build_object(
                'id', s.id,
                'code', s.code,
                'created_at', s.created_at,
                'is_fast', s.is_fast,
                'current_turn_user_id', ctd.current_turn_user_id,
                'duel_phase', COALESCE(ctd.duel_phase, ''),
                'n_rounds', COALESCE(rd.n_rounds, 0),
                'n_questions_per_round', s.n_questions_per_round,
                'selection_method', s.selection_method,
                'duel_status', s.duel_status,
                'winner_id', s.winner_id,
                'current_turn_start_time', ctd.current_turn_start_time,
                'tournament_id', s.tournament_id,
                'questions_and_answers', COALESCE(qd.questions_and_answers, '[]'::jsonb),
                'participations', COALESCE(pd.participations, '[]'::jsonb),
                'rounds', COALESCE(rd.rounds, '[]'::jsonb)
            )
        ), '[]'::jsonb)::text AS data
        FROM quiz_session s
        LEFT JOIN question_data qd ON qd.session_id = s.id
        LEFT JOIN participation_data pd ON pd.session_id = s.id
        LEFT JOIN round_data rd ON rd.duel_id = s.id
        LEFT JOIN current_turn_data ctd ON ctd.session_id = s.id
        WHERE s.id = ANY(%s)
    """
    with connection.cursor() as cursor:
        cursor.execute(query, [ids_list, ids_list, ids_list, ids_list, ids_list])
        row = cursor.fetchone()
        # We know this will return a row because we have a COALESCE in the query
        # that ensures we get at least an empty array
        duel_data = json.loads(row[0])

    questions_and_answers = [
        question for duel in duel_data for question in duel["questions_and_answers"]
    ]
    quiz_utils.update_urls_from_orm(questions_and_answers)

    try:
        return duel_data[0] if isinstance(duel_ids, int) else duel_data
    except IndexError:
        raise DuelNotFound
