import quiz.duel_service as duel_service
import quiz.session_service as session_service
from api.controllers.users import FlexiblePageNumberPagination
from api.schemas.users import SimpleUserOut
from asgiref.sync import sync_to_async
from currency.currency_service import InsufficientFundsError
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import paginate
from quiz.schemas.duels import (
    DuelAddQuestionsIn,
    DuelIn,
    DuelInviteIn,
    DuelJoinByCodeIn,
    DuelJoinByTournamentIn,
    DuelOut,
    DuelQuestionIdIn,
    DuelSubmitAnswerIn,
)

duel_router = Router()


@duel_router.post(
    "",
    response={201: DuelOut},
    url_name="duel_list",
)
async def duel_create(request: HttpRequest, duel_in: DuelIn):
    user = request.auth
    try:
        return await duel_service.acreate_and_prepare_duel(
            user,
            duel_in.user_id,
            duel_in.n_rounds,
            duel_in.n_questions_per_round,
            duel_in.selection_method,
            duel_in.question_blocks,
            duel_in.topic,
            duel_in.subject,
            duel_in.is_fast,
            duel_in.tournament_id,
        )
    except duel_service.UserAlreadyInDuel as e:
        raise HttpError(400, str(e))
    except InsufficientFundsError as e:
        raise HttpError(400, str(e))
    except ValidationError as e:
        raise HttpError(400, str(e))
    except duel_service.TournamentNotActive:
        raise HttpError(400, "Tournament is not active")
    except duel_service.TournamentNotFound:
        raise HttpError(404, "Tournament not found")


@duel_router.get(
    "/{id}/detail",
    response={200: DuelOut},
    url_name="duel_detail",
)
async def duel_detail(request, id: int):
    try:
        return await sync_to_async(duel_service.get_duel_out)(id)
    except duel_service.DuelNotFound:
        raise HttpError(404, "Duel not found")


@duel_router.get("", response={200: list[DuelOut]}, url_name="duel_list")
async def duel_list(request):
    user = request.auth
    return await sync_to_async(duel_service.list_duels)(user.id)


@duel_router.get(
    "/attack-suggestions",
    response={200: list[SimpleUserOut]},
    url_name="duel_attack_suggestions",
)
@paginate(FlexiblePageNumberPagination)
async def duel_attack_suggestions(request):
    user = request.auth
    return await duel_service.get_attack_suggestions(user.id)


@duel_router.patch(
    "/join-by-code",
    response={200: DuelOut},
    url_name="duel_join_by_code",
)
async def join_duel_by_code(request: HttpRequest, code_in: DuelJoinByCodeIn):
    user = request.auth
    try:
        return await sync_to_async(duel_service.join_duel_by_code)(user, code_in.code)
    except duel_service.DuelIsFull:
        raise HttpError(400, "Duel is full")
    except duel_service.DuelNotFound:
        raise HttpError(404, "Duel not found")
    except duel_service.UserAlreadyInDuel:
        raise HttpError(400, "User already in duel")


@duel_router.patch(
    "/join-by-tournament",
    response={200: DuelOut},
    url_name="duel_join_by_tournament",
)
async def duel_join_by_tournament(
    request: HttpRequest, duel_join_by_tournament_in: DuelJoinByTournamentIn
):
    user = request.auth
    try:
        duel = await sync_to_async(duel_service.join_duel_by_tournament)(
            user.id,
            duel_join_by_tournament_in.tournament_id,
        )
    except duel_service.DuelNotFound:
        raise HttpError(404, "Duel not found")
    except duel_service.UserAlreadyInDuel:
        raise HttpError(400, "User already in duel")
    return duel


@duel_router.patch(
    "/{id}/invite",
    response={204: None},
    url_name="duel_invite",
)
async def duel_invite(request: HttpRequest, id: int, duel_invite_in: DuelInviteIn):
    user = request.auth
    try:
        await sync_to_async(duel_service.invite_to_duel)(
            user, duel_invite_in.user_id, id
        )
    except duel_service.DuelIsFull:
        raise HttpError(400, "Duel is full")


@duel_router.patch(
    "/{id}/add-questions",
    response={204: None},
    url_name="duel_add_questions",
)
async def duel_add_questions(
    request: HttpRequest, id: int, duel_in: DuelAddQuestionsIn
):
    user = request.auth
    try:
        await sync_to_async(duel_service.add_questions_to_duel_by_query)(
            user_id=user.id,
            duel_id=id,
            query=duel_in.query,
            area=duel_in.area,
            source_filter=duel_in.source_filter,
            difficulty=duel_in.difficulty,
            is_fast=duel_in.is_fast,
        )
    except duel_service.CannotAddQuestionsToNonQueryOfficialDuel:
        raise HttpError(400, "Cannot add questions to non-query official duel")
    except duel_service.DuelNotFound:
        raise HttpError(404, "Duel not found")


@duel_router.patch(
    "/{id}/confirm",
    response={204: None},
    url_name="duel_confirm",
)
async def duel_confirm(request: HttpRequest, id: int):
    user = request.auth
    await sync_to_async(duel_service.confirm_duel_participant)(user, id)


@duel_router.patch(
    "/{id}/reject",
    response={204: None},
    url_name="duel_reject",
)
async def duel_reject(request: HttpRequest, id: int):
    user = request.auth
    await sync_to_async(duel_service.reject_duel_participant)(user.id, id)


@duel_router.patch(
    "/{id}/question-seen",
    response={204: None},
    url_name="duel_question_seen",
)
async def duel_question_seen(
    request: HttpRequest, id: int, question_id_in: DuelQuestionIdIn
):
    user = request.auth
    await sync_to_async(duel_service.mark_question_seen)(
        user.id, id, question_id_in.question_id
    )


@duel_router.patch(
    "/{id}/question-timed-out",
    response={204: None},
    url_name="duel_question_timed_out",
)
async def duel_question_timed_out(
    request: HttpRequest, id: int, question_id_in: DuelQuestionIdIn
):
    user = request.auth
    await sync_to_async(duel_service.mark_question_timed_out)(
        user, id, question_id_in.question_id
    )


@duel_router.patch(
    "/{id}/submit-answer",
    response={204: None},
    url_name="duel_submit_answer",
)
async def duel_submit_answer(
    request: HttpRequest, id: int, duel_submit_answer_in: DuelSubmitAnswerIn
):
    user = request.auth
    if duel_submit_answer_in.answer_choice_id is None:
        await sync_to_async(duel_service.mark_question_timed_out)(
            user, id, duel_submit_answer_in.question_id
        )
    else:
        try:
            await sync_to_async(duel_service.submit_answer)(
                user,
                id,
                duel_submit_answer_in.question_id,
                duel_submit_answer_in.answer_choice_id,
            )
        except session_service.NoRowsAffectedError:
            raise HttpError(400, "Either answer was already submitted or timed out")
