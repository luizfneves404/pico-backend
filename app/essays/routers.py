from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, status

from app.currency.currency_service import InsufficientFundsError
from app.deps import CurrentUserAnnotated, CurrentUserDep, DBSessionAnnotated
from app.essays import service as essay_service
from app.essays.schemas import (
    EssayCorrectionIn,
    EssayOut,
    EssayTopicIn,
    EssayTopicOut,
)

router = APIRouter(
    prefix="/essay-topics", tags=["essay-topics"], dependencies=[CurrentUserDep]
)


@router.get("", response_model=list[EssayTopicOut])
async def essay_topic_list(
    db_session: DBSessionAnnotated, current_user: CurrentUserAnnotated
):
    return await essay_service.list_essay_topics(db_session, current_user.id)


@router.post("", response_model=EssayTopicOut, status_code=status.HTTP_200_OK)
async def essay_topic_start(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    essay_topic_in: EssayTopicIn,
):
    try:
        return await essay_service.start_essay_topic(
            db_session, current_user.id, essay_topic_in.name
        )
    except essay_service.EssayTopicNameRequiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Name cannot be empty"
        )


@router.get("/{id}", response_model=EssayTopicOut)
async def essay_topic_detail(
    db_session: DBSessionAnnotated, id: int, current_user: CurrentUserAnnotated
):
    try:
        return await essay_service.get_essay_topic(db_session, current_user.id, id)
    except essay_service.EssayTopicNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Essay topic not found"
        )


@router.post("/{id}/submit", response_model=EssayOut, status_code=status.HTTP_200_OK)
async def essay_topic_submit_essay(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
    upload: UploadFile,
    essay_type: Annotated[str, Form()] = "Enem",
):
    essay_topic_id = id
    try:
        return await essay_service.submit_essay_with_file(
            db_session, current_user, essay_topic_id, essay_type, upload
        )
    except essay_service.EssayTopicNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Essay topic not found"
        )
    except essay_service.EssayTypeNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Essay type not found"
        )
    except essay_service.InvalidContentTypeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File content type '{e.args[0]}' not supported",
        )
    except essay_service.InvalidMIMETypeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{e.args[0]}' not supported",
        )
    except InsufficientFundsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{id}/correct", response_model=EssayOut)
async def essay_topic_correct_essay(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
    essay_correction_in: EssayCorrectionIn,
):
    essay_topic_id = id

    try:
        return await essay_service.correct_essay(
            db_session,
            current_user.id,
            essay_topic_id,
            essay_correction_in.essay_type,
            essay_correction_in.user_corrected_text,
        )
    except essay_service.EssayTopicNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Essay topic not found"
        )
    except essay_service.EssayTypeNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Essay type not found"
        )
