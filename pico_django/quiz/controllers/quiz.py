import quiz.quiz_service as quiz_service
import quiz.session_pdf as session_pdf
import quiz.stats_service as stats_service
from currency.currency_service import InsufficientFundsError
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from ninja import File, Form, Router
from ninja.errors import HttpError
from ninja.files import UploadedFile
from quiz.models import SelectionSource
from quiz.schemas.answers import AnswerDayOut
from quiz.schemas.quiz import (
    AddQuestionsToQuizIn,
    GenerateQuizIn,
    NewSubmitMultipleChoiceAnswerIn,
    OtherUserQuizOut,
    PersonalizedQuizIn,
    QuizIn,
    QuizOut,
    SubmitMultipleChoiceAnswerIn,
    SubmitOpenEndedAnswerIn,
    WhatsAppQuizIn,
)

quiz_router = Router()


@quiz_router.get("", response={200: list[QuizOut]}, url_name="quiz_list")
async def quiz_list(request: HttpRequest):
    user = request.auth
    return await quiz_service.list_quizzes(user)


@quiz_router.get(
    "/user_quizzes/{user_id}",
    response={200: list[OtherUserQuizOut]},
    url_name="user_quizzes",
)
async def user_quizzes(request: HttpRequest, user_id: int):
    return await quiz_service.alist_user_quizzes(user_id)


@quiz_router.post(
    "",
    response={201: QuizOut, 200: QuizOut},
    url_name="quiz_list",
)
async def create_quiz(request: HttpRequest, quiz_in: QuizIn):
    user = request.auth
    try:
        quiz = await quiz_service.create_quiz(
            user,
            quiz_in.query,
            quiz_in.n_questions,
            quiz_in.area,
            quiz_in.source_filter,
            quiz_in.difficulty,
            quiz_in.question_type,
            quiz_in.parent_quiz_id,
        )
    except InsufficientFundsError as e:
        raise HttpError(400, str(e))
    except ValidationError as e:
        raise HttpError(400, str(e))
    return 201, quiz


@quiz_router.post(
    "/with-files/create",
    response={201: QuizOut, 200: QuizOut},
    url_name="create_quiz_with_files",
)
async def create_quiz_with_files(
    request: HttpRequest,
    topic: Form[str],
    selection_source: Form[SelectionSource],
    files: File[list[UploadedFile]] = [],
):
    user = request.auth
    try:
        quiz = await quiz_service.create_quiz(
            user,
            topic,
            quiz_in.n_questions,
            quiz_in.area,
            quiz_in.source_filter,
            quiz_in.difficulty,
            quiz_in.question_type,
            list(files),
        )
    except InsufficientFundsError as e:
        raise HttpError(400, str(e))
    except ValidationError as e:
        raise HttpError(400, str(e))
    return 201, quiz


@quiz_router.post(
    "/{id}/add-questions",
    response={200: QuizOut},
    url_name="add_questions_to_quiz",
)
async def add_questions_to_quiz(
    request: HttpRequest, id: int, add_questions_in: AddQuestionsToQuizIn
):
    user = request.auth
    try:
        quiz = await quiz_service.add_questions_to_quiz(
            id,
            add_questions_in.selection_method,
            add_questions_in.n_questions,
            add_questions_in.question_density,
            add_questions_in.area,
            add_questions_in.source_filter,
            add_questions_in.difficulty,
            add_questions_in.question_type,
        )
    except quiz_service.QuizNotFound:
        raise HttpError(404, "Quiz not found")
    return quiz


@quiz_router.post(
    "/personalized/create",
    response={201: QuizOut, 200: QuizOut},
    url_name="create_personalized_quiz",
)
async def create_personalized_quiz(request: HttpRequest, quiz_in: PersonalizedQuizIn):
    user = request.auth

    try:
        quiz = await quiz_service.acreate_personalized_quiz(
            user=user,
            question_type=quiz_in.question_type,
        )
    except InsufficientFundsError as e:
        raise HttpError(400, str(e))
    except ValidationError as e:
        raise HttpError(400, str(e))

    return 201, quiz


@quiz_router.get("/{id}", response={200: QuizOut}, url_name="quiz_detail")
async def quiz_detail(request: HttpRequest, id: int):
    user = request.auth
    try:
        return await quiz_service.read_quiz(user, id)
    except quiz_service.QuizNotFound:
        raise HttpError(404, "Quiz not found")


@quiz_router.get("/redeem/{code}", response={200: QuizOut}, url_name="quiz_redeem")
async def quiz_redeem(request: HttpRequest, code: str):
    user = request.auth
    try:
        return await quiz_service.redeem_quiz(user, code)
    except quiz_service.QuizNotFound:
        raise HttpError(404, "Quiz not found")
    except InsufficientFundsError as e:
        raise HttpError(400, str(e))


@quiz_router.get("/{id}/pdf", response={200: str}, url_name="quiz_pdf")
async def quiz_pdf(request: HttpRequest, id: int):
    try:
        return await session_pdf.get_session_pdf_url(id)
    except session_pdf.SessionNotFound:
        raise HttpError(404, "Quiz not found")


@quiz_router.post(
    "/{id}/submit",
    response={204: None},
    url_name="quiz_submit_multiple_choice",
)
async def quiz_submit_multiple_choice_answer(
    request: HttpRequest,
    id: int,
    quiz_answers: SubmitMultipleChoiceAnswerIn | NewSubmitMultipleChoiceAnswerIn,
):
    user = request.auth
    quiz_id = id
    try:
        if isinstance(quiz_answers, NewSubmitMultipleChoiceAnswerIn):
            return await quiz_service.asubmit_multiple_choice_answer(
                user.id,
                quiz_id,
                quiz_answers.question_id,
                quiz_answers.answer_choice_id,
            )
        else:
            return await quiz_service.asubmit_multiple_choice_answer(
                user.id,
                quiz_id,
                quiz_answers.answers.question_id,
                quiz_answers.answers.answer_choice_id,
            )
    except quiz_service.QuizNotFound:
        raise HttpError(404, "Quiz not found")
    except quiz_service.ChoiceNotInQuestionError as e:
        raise HttpError(400, str(e))
    except quiz_service.QuestionNotFoundInQuiz as e:
        raise HttpError(400, str(e))


@quiz_router.post(
    "/{id}/submit/open-ended",
    url_name="quiz_submit_open_ended",
)
async def quiz_submit_open_ended_answers(
    request: HttpRequest, id: int, answer_in: SubmitOpenEndedAnswerIn
):
    user = request.auth
    try:
        response = await quiz_service.asubmit_open_ended_answers(
            user.id,
            id,
            answer_in.question_id,
            answer_in.submitted_text,
        )
    except quiz_service.QuestionNotFoundInQuiz:
        raise HttpError(400, "Question not found in quiz")
    except quiz_service.QuestionAlreadyAnswered:
        raise HttpError(400, "Question already answered")
    response["Cache-Control"] = "no-cache"
    response["Transfer-Encoding"] = "chunked"
    return response


@quiz_router.get(
    "/personalization/suggestions",
    response={200: list[str]},
    url_name="quiz_personalization_suggestions",
)
async def quiz_personalization_suggestions(request: HttpRequest):
    user = request.auth
    return await stats_service.aidentify_weak_subcategories(user.id)


answers_router = Router()


@answers_router.get(
    "",
    response={200: list[AnswerDayOut]},
    url_name="answers_list",
)
async def answers_list(request: HttpRequest):
    user = request.auth
    return await quiz_service.get_answers_grouped_by_day(user)


@answers_router.post(
    "/query/quiz_pdf",
    response={201: str, 200: str},
)
async def query_to_pdf(request: HttpRequest, quiz_in: WhatsAppQuizIn):
    user = request.auth
    quiz = await quiz_service.create_quiz_whatsapp(
        user,
        quiz_in.query,
        quiz_in.n_questions,
        area=quiz_in.area,
        source_filter=quiz_in.source_filter,
    )

    try:
        pdf_url = await session_pdf.get_session_pdf_url(quiz.id)
    except session_pdf.SessionNotFound:
        raise HttpError(404, "Quiz not found")

    return 201, pdf_url


@quiz_router.post("/transcription/generate", response={201: QuizOut})
async def generate_quiz_from_transcriptions(
    request: HttpRequest,
    create_in: GenerateQuizIn,
):
    user = request.auth
    quiz_out = await quiz_service.generate_quiz_from_transcriptions_or_topic(
        user=user,
        is_fast=create_in.is_fast,
        question_blocks=create_in.question_blocks,
        topic=create_in.topic,
        question_type=create_in.question_type,
        n_questions_per_block=create_in.n_questions_per_block,
        n_questions_for_topic=create_in.n_questions_for_topic,
        subject=create_in.subject,
    )
    return 201, quiz_out
