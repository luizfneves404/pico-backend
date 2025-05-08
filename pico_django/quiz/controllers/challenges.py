import quiz.challenge_service as challenge_service
import quiz.session_service as session_service
from asgiref.sync import sync_to_async
from currency.currency_service import InsufficientFundsError
from ninja import Router
from ninja.errors import HttpError
from quiz.schemas.challenge import (
    ChallengeCreateIn,
    ChallengeInviteIn,
    ChallengeJoinByCodeIn,
    ChallengeOut,
    ChallengeQuestionIdIn,
    ChallengeQuestionOut,
    ChallengeSubmitAnswerIn,
)

challenge_router = Router()


@challenge_router.post(
    "",
    response={201: ChallengeOut},
    url_name="challenge_list",
)
async def create_challenge(request, challenge_create_in: ChallengeCreateIn):
    user = request.auth
    try:
        data = await challenge_service.acreate_and_prepare_challenge(
            user,
            to_user_ids=challenge_create_in.user_ids,
            start_time=challenge_create_in.start_time,
            end_time=challenge_create_in.end_time,
            selection_method=challenge_create_in.selection_method,
            query=challenge_create_in.query,
            question_blocks=challenge_create_in.question_blocks,
            topic=challenge_create_in.topic,
            subject=challenge_create_in.subject,
            area=challenge_create_in.area,
            difficulty=challenge_create_in.difficulty,
            source_filter=challenge_create_in.source_filter,
            is_fast=challenge_create_in.is_fast,
        )
        return data
    except InsufficientFundsError:
        raise HttpError(400, "Insufficient funds")


@challenge_router.get(
    "/{id}/detail",
    response={200: ChallengeOut},
    url_name="challenge_detail",
)
async def challenge_detail(request, id: int):
    user = request.auth
    try:
        return await sync_to_async(challenge_service.prepare_challenges)(user.id, id)
    except challenge_service.ChallengeNotFound:
        raise HttpError(404, "Challenge not found")


@challenge_router.get("", response={200: list[ChallengeOut]}, url_name="challenge_list")
async def challenge_list(request):
    user = request.auth
    return await sync_to_async(challenge_service.list_challenges)(user.id)


@challenge_router.get(
    "/{id}/questions/{question_id}/detail",
    response={200: ChallengeQuestionOut},
    url_name="challenge_question_detail",
)
async def get_challenge_question_detail(request, id: int, question_id: int):
    try:
        return await sync_to_async(challenge_service.get_challenge_question_detail)(
            id, question_id
        )
    except challenge_service.QuestionNotFound:
        raise HttpError(404, "Question not found")


@challenge_router.patch(
    "/{id}/invite",
    response={204: None},
    url_name="challenge_invite",
)
async def invite_to_challenge(request, id: int, challenge_invite_in: ChallengeInviteIn):
    user = request.auth
    await sync_to_async(challenge_service.invite_to_challenge)(
        user, id, challenge_invite_in.user_ids
    )


@challenge_router.patch(
    "/join-by-code",
    response={200: ChallengeOut},
    url_name="challenge_join_by_code",
)
async def join_challenge_by_code(request, challenge_join_in: ChallengeJoinByCodeIn):
    user = request.auth
    try:
        return await challenge_service.join_challenge_by_code(
            user, challenge_join_in.challenge_code
        )
    except (
        challenge_service.ChallengeNotFound
    ):  # TODO: this never runs since code doesnt raise it
        raise HttpError(404, "Challenge not found")
    except challenge_service.UserAlreadyInChallenge:
        raise HttpError(400, "User already in challenge")
    except InsufficientFundsError as e:
        raise HttpError(400, str(e))


@challenge_router.patch(
    "/{id}/question-seen",
    response={204: None},
    url_name="challenge_question_seen",
)
async def challenge_question_seen(
    request, id: int, question_id_in: ChallengeQuestionIdIn
):
    user = request.auth
    try:
        await sync_to_async(challenge_service.mark_question_seen)(
            user.id, id, question_id_in.question_id
        )
    except session_service.SessionQuestionNotFoundError:
        raise HttpError(404, "Session question not found")


@challenge_router.patch(
    "/{id}/question-timed-out",
    response={204: None},
    url_name="challenge_question_timed_out",
)
async def challenge_question_timed_out(
    request, id: int, question_id_in: ChallengeQuestionIdIn
):
    user = request.auth
    await sync_to_async(challenge_service.mark_question_timed_out)(
        user.id, id, question_id_in.question_id
    )


@challenge_router.patch(
    "/{id}/submit-answer",
    response={204: None},
    url_name="challenge_submit_answer",
)
async def submit_challenge_answer(
    request, id: int, challenge_submit_in: ChallengeSubmitAnswerIn
):
    user = request.auth
    try:
        return await sync_to_async(challenge_service.submit_answer)(
            user.id,
            id,
            challenge_submit_in.question_id,
            challenge_submit_in.answer_choice_id,
        )
    except session_service.NoRowsAffectedError:
        raise HttpError(400, "Either answer was already submitted or timed out")


@challenge_router.patch(
    "/{id}/confirm",
    response={204: None},
    url_name="challenge_confirm",
)
async def challenge_confirm(request, id: int):
    user = request.auth
    try:
        await challenge_service.confirm_challenge_participant(user, id)
    except InsufficientFundsError as e:
        raise HttpError(400, str(e))


@challenge_router.patch(
    "/{id}/reject",
    response={204: None},
    url_name="challenge_reject",
)
async def challenge_reject(request, id: int):
    user = request.auth
    await sync_to_async(challenge_service.reject_challenge_participant)(user.id, id)
