import logging

import api.services.misc_service as misc_service
from api.schemas.misc import CommandOut
from commands.commands_utils.common import CommandRegistry
from ninja import File, Router
from ninja.files import UploadedFile

logger = logging.getLogger(__name__)

router = Router()

API_FORCE_UPDATE_VERSION = 1


@router.get("commands", response=list[CommandOut], url_name="commands_list")
async def commands_list(request):
    return [
        CommandOut(
            name=command,
            description=description,
        )
        for command, description in CommandRegistry.get_commands_and_descriptions()
    ]


@router.post("/transcription/generate", response={200: list[str]})
async def generate_transcription(request, files: File[list[UploadedFile]]):
    return await misc_service.generate_transcription(files)


@router.get("/api-force-update-version", response={200: int})
async def api_force_update_version(request):
    return API_FORCE_UPDATE_VERSION
