from asgiref.sync import sync_to_async
from ninja import Router
from ninja.errors import HttpError
from shared.code_generation import InvalidCodeError

import challenges.tournament_service as tournaments_service

from .schemas import (
    DetailedTournament,
    SchoolInTournamentRanking,
    SimpleTournament,
    TournamentCodeIn,
)

tournaments_router = Router()


@tournaments_router.get("", response=list[SimpleTournament], url_name="tournament_list")
async def tournament_list(request):
    return await tournaments_service.alist_tournaments(request.auth.id)


@tournaments_router.get(
    "/{tournament_id}/detail", response=DetailedTournament, url_name="tournament_detail"
)
async def tournament_detail(request, tournament_id: int):
    try:
        return await sync_to_async(tournaments_service.prepare_detailed_tournament)(
            tournament_id
        )
    except tournaments_service.TournamentNotFoundError:
        raise HttpError(404, "Tournament not found")


@tournaments_router.post(
    "/join-by-code",
    response={200: DetailedTournament},
    url_name="tournament_join_by_code",
)
async def tournament_join_by_code(request, tournament_code_in: TournamentCodeIn):
    try:
        return await sync_to_async(tournaments_service.join_tournament_by_code)(
            tournament_code_in.tournament_code, request.auth.id
        )
    except tournaments_service.TournamentNotFoundError:
        raise HttpError(404, "Tournament not found")
    except tournaments_service.UserAlreadyInTournamentError:
        raise HttpError(400, "User already in tournament")
    except InvalidCodeError:
        raise HttpError(400, "Invalid code")


@tournaments_router.get(
    "/{tournament_id}/has-pending-duels",
    response=bool,
    url_name="tournament_has_pending_duels",
)
async def tournament_has_pending_duels(request, tournament_id: int):
    return await sync_to_async(tournaments_service.has_pending_duels)(tournament_id)


@tournaments_router.get(
    "/{tournament_id}/school-ranking",
    response=list[SchoolInTournamentRanking],
    url_name="tournament_school_ranking",
)
async def tournament_school_ranking(request, tournament_id: int):
    return await sync_to_async(tournaments_service.get_school_ranking)(tournament_id)
