import api.services.file_service as file_service
from api.schemas.files import FileGroupOut, FileOut
from api.utils import validate_chatroom_membership_members_prefetched
from ninja import Router

router = Router()


@router.get(
    "/chatrooms/{chatroom_id}/files",
    response=list[FileOut],
    url_name="list_chatroom_files",
)
async def list_chatroom_files(request, chatroom_id: int):
    user = request.auth
    chatroom = await validate_chatroom_membership_members_prefetched(chatroom_id, user)
    files = await file_service.list_files_for_chatroom(chatroom)
    for embedded_file in files:
        setattr(embedded_file, "filename", embedded_file.file.name.split("/")[-1])
    return files


@router.get(
    "/files-groups",
    response=list[FileGroupOut],
    url_name="list_file_groups",
)
async def list_file_groups(request):
    return await file_service.list_file_groups()
