import quiz.question_service as question_service
from ninja import Router
from ninja.errors import HttpError
from quiz.schemas.quiz import DetailedQuestionOut

router = Router()


@router.get(
    "/{id}",
    response={200: DetailedQuestionOut},
    url_name="question_detail",
)
async def question_detail(request, id: int):
    try:
        return await question_service.get_detailed_question(id)
    except question_service.QuestionNotFound:
        raise HttpError(404, "Question not found")
