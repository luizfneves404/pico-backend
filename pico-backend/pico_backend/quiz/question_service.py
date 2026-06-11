import asyncio
import logging
import random
import string
from datetime import timedelta
from typing import Any

import shared.openai_utils as openai_utils
from api.models import User
from asgiref.sync import sync_to_async
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from pgvector.django import CosineDistance
from pydantic import BaseModel
from pylatexenc.latex2text import LatexNodes2Text
from shared import ai_utils, file_utils, gemini_utils

from quiz import stats_service
from quiz.models import (
    CUSTOM_SOURCE,
    ENEM_AREAS,
    SUBJECT_TO_AREA,
    Choice,
    Question,
    QuestionQuerySet,
    QuestionType,
    SessionQuestionUser,
    Transcription,
)
from quiz.utils import (
    SUBCATEGORIES_TO_PARENT_CATEGORIES,
)

from .constants import (
    SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION,
    SYSTEM_MESSAGE_QUESTION_GENERATION_THEME,
    SYSTEM_MESSAGE_QUESTION_GENERATION_THEME_MATH,
    USER_MESSAGE_QUESTION_GENERATION_DESCRIPTION_MATH,
)

logger = logging.getLogger(__name__)

NUM_QUESTIONS_FOR_ALREADY_ANSWERED = 800

DAYS_AGO_TO_EXCLUDE_RECENT_ANSWERS = 7

COLLEGE_TO_EXAM = {
    "UFRJ": "ENEM",
    "USP": "FUVEST",
    "PUC": "PUC-Rio",
    "FGV": "FGV",
    "UERJ": "UERJ",
}

VALID_MIME_TYPES_FOR_TRANSCRIPTION = [
    "image/jpeg",
    "image/png",
    "image/jpg",
    "application/pdf",
]

FILES_PER_BLOCK = 5

TOKENS_PER_BLOCK = 300


class QuestionNotFound(Exception):
    pass


class QuestionInstance(BaseModel):
    text: str
    choices: list[str]
    correct_choice: str


class QuestionSet(BaseModel):
    questions: list[QuestionInstance]


def create_questions(
    questions: list[str], answers: list[str], source: str = ""
) -> list[Question]:
    embeddings = openai_utils.compute_embedding(questions)
    exam_questions = Question.objects.bulk_create(
        [
            Question(
                text=question,
                answer_text=answer,
                source=source,
                embedding=embedding,
            )
            for question, answer, embedding in zip(questions, answers, embeddings)
        ]
    )
    logger.debug(f"Created {len(exam_questions)} questions")
    return exam_questions


def create_question(question: str, answer: str, source: str = "") -> Question:
    embedding = openai_utils.compute_embedding(question)
    return Question.objects.create(
        question=question, answer=answer, source=source, embedding=embedding
    )


async def get_detailed_question(id: int) -> Question:
    question = (
        await Question.objects.filter(id=id)
        .prefetch_related("choices", "session_question_set__session_question_user_set")
        .afirst()
    )
    if question is None:
        raise QuestionNotFound

    # Total number of users who answered this question
    total_answers = sum(
        len(sq.session_question_user_set.all())
        for sq in question.session_question_set.all()
    )

    # create choices list with all fields of DetailedChoiceOut
    choices: list[dict[str, Any]] = []
    for choice in question.choices.all():
        # Count the number of users who selected this particular choice
        choice_answers_count = sum(
            len(
                [
                    squ
                    for squ in sq.session_question_user_set.all()
                    if squ.choice_id == choice.id
                ]
            )
            for sq in question.session_question_set.all()
        )

        # Calculate the percentage of users who selected this choice
        if total_answers > 0:
            percentage_users_answered = (choice_answers_count / total_answers) * 100
        else:
            percentage_users_answered = 0.0

        choices.append(
            {
                "id": choice.id,
                "text": choice.text,
                "image": choice.image,
                "is_correct": choice.is_correct,
                "percentage_users_answered": percentage_users_answered,
            }
        )

    setattr(question, "detailed_choices", choices)

    return question


def get_official_questions(
    query: str,
    n: int,
    *,
    area: str = "",
    subject: str = "",
    source_filter: str = "",
    difficulty: str = "",
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE,
    excluded_ids: list[int] = [],
    excluded_session_ids: list[int] = [],
    excluded_user_id: int | None = None,
    is_fast: bool | None = None,
) -> QuestionQuerySet:
    """
    Get official questions from the database.

        query (str): The query to search for with embeddings.
        n (int): The number of questions to return.
        area (str, optional): The area to filter by. Defaults to "".
        subject (str, optional): The subject to filter by. Defaults to "".
        source_filter (str, optional): The source to filter by. Defaults to "".
        difficulty (str, optional): The difficulty to filter by. Defaults to "".
        question_type (QuestionType, optional): The type of question to filter by. Defaults to QuestionType.MULTIPLE_CHOICE.
        excluded_ids (list[int], optional): The ids of the questions to exclude. Defaults to [].
        excluded_session_ids (list[int], optional): The ids of the sessions to exclude. Defaults to [].
        excluded_user_id (int | None, optional): The id of a user whose recent answers will be used to exclude questions. Defaults to None.
        is_fast (bool | None, optional): Whether the questions are fast mode questions. Defaults to None.

    Returns:
        QuestionQuerySet: A queryset of questions.
    """
    embedding = openai_utils.compute_embedding(query) if query else None
    filters = {}

    if area and area in ENEM_AREAS:
        filters["subject__in"] = ENEM_AREAS[area]
    if subject and any(subject in subjects for subjects in ENEM_AREAS.values()):
        filters["subject"] = subject
    if source_filter:
        filters["source__icontains"] = source_filter
    if difficulty:
        filters["difficulty"] = difficulty
    if is_fast:
        filters["is_fast"] = is_fast

    queryset = Question.objects.all()

    if filters:
        queryset = queryset.filter(**filters)

    if embedding:
        queryset = queryset.order_by(CosineDistance("embedding", embedding))
    else:
        queryset = queryset.order_by("?")

    if question_type:
        queryset = queryset.filter_by_type(question_type)

    if excluded_ids:
        queryset = queryset.exclude(id__in=excluded_ids)

    if excluded_session_ids:
        queryset = queryset.exclude(
            session_question_set__session_id__in=excluded_session_ids
        )

    if excluded_user_id:
        # Only exclude questions answered by the user in the last 7 days
        seven_days_ago = timezone.now() - timedelta(
            days=DAYS_AGO_TO_EXCLUDE_RECENT_ANSWERS
        )
        queryset = queryset.exclude(
            session_question_set__session_question_user_set__user_id=excluded_user_id,
            session_question_set__session_question_user_set__timestamp__gt=seven_days_ago,
        )

    queryset = queryset.exclude_inactive().exclude(source=CUSTOM_SOURCE)

    # If no source filter is specified, ensure 60% of questions are from privileged sources
    if not source_filter:
        privileged_sources = [
            "ENEM",
            "ENEM PPL",
            "FUVEST",
            "PUC-Rio",
            "FGV",
            "UNICAMP",
            "UERJ",
        ]

        privileged_q = Q()
        for source in privileged_sources:
            privileged_q |= Q(source__startswith=source)

        privileged_count = int(n * 0.6)
        regular_count = n - privileged_count

        # Get questions from privileged sources
        privileged_queryset = queryset.filter(privileged_q)
        privileged_ids = list(
            privileged_queryset.values_list("id", flat=True)[:privileged_count]
        )

        # If we couldn't get enough privileged questions, adjust regular_count
        if len(privileged_ids) < privileged_count:
            regular_count += privileged_count - len(privileged_ids)

        # Get remaining questions from any source, excluding those already selected
        remaining_queryset = queryset.exclude(id__in=privileged_ids)
        remaining_ids = list(
            remaining_queryset.values_list("id", flat=True)[:regular_count]
        )

        combined_ids = privileged_ids + remaining_ids

        final_queryset = Question.objects.filter(id__in=combined_ids)

        return final_queryset

    return queryset[:n]


def get_personalized_questions(
    n: int,
    question_type: QuestionType,
    user: User,
    parent_quiz_id: int | None = None,
):
    selector = PersonalizedQuestionSelector(user.id, parent_quiz_id)

    total_questions = n
    learning_questions = n // 2
    questions = selector.get_questions(total_questions, learning_questions)

    AREA_PRIORITY = {
        "Linguagens": 1,
        "Ciências Humanas": 2,
        "Ciências da Natureza": 3,
        "Matemática": 4,
    }

    def get_area_priority(question: Question):
        area = SUBJECT_TO_AREA.get(question.subject, None)
        return AREA_PRIORITY.get(area, 5)

    questions = sorted(questions, key=get_area_priority)

    return questions


class PersonalizedQuestionSelector:
    def __init__(self, user_id: int, parent_quiz_id: int | None = None):
        self.user_id = user_id
        self.excluded_ids: set[int] = set()
        self.recently_answered_ids: set[int] = self._get_recently_answered_ids()
        if parent_quiz_id:
            self.parent_related_ids: set[int] = self._get_parent_related_question_ids(
                parent_quiz_id
            )
        else:
            self.parent_related_ids: set[int] = set()

        self.excluded_ids.update(self.parent_related_ids)

        logger.debug(f"Initialized QuestionSelector for user_id: {user_id}")

    def get_questions(
        self, total_questions: int, weakest_questions: int
    ) -> list[Question]:
        logger.info(f"Getting {total_questions} questions for user_id: {self.user_id}")

        strategies = [
            (self._get_weak_subcategory_questions, weakest_questions),
            (self._get_weak_category_questions, weakest_questions),
            (self._get_exploring_questions, total_questions),
            (self._get_random_questions, total_questions),
        ]

        questions: list[Question] = []
        learning_questions = 0
        for strategy, limit in strategies:
            if len(questions) < total_questions:
                remaining = min(
                    total_questions - len(questions), limit - learning_questions
                )
                if remaining > 0:
                    new_questions = strategy(remaining)
                    questions.extend(new_questions)
                    self.excluded_ids.update(q.id for q in new_questions)
                    if strategy in [
                        self._get_weak_subcategory_questions,
                        self._get_weak_category_questions,
                    ]:
                        learning_questions += len(new_questions)
                    logger.debug(
                        f"Added {len(new_questions)} questions from {strategy.__name__}"
                    )
            else:
                break

        logger.info(f"Total questions selected: {len(questions)}")
        return questions[:total_questions]

    def _get_weak_subcategory_questions(self, count: int) -> list[Question]:
        weak_subcategories = stats_service.identify_weak_subcategories(self.user_id)
        logger.debug(f"Weak subcategories: {weak_subcategories}")
        return self._get_questions_for_subcategories(weak_subcategories, count)

    def _get_weak_category_questions(self, count: int) -> list[Question]:
        weak_subcategories = stats_service.identify_weak_subcategories(self.user_id)
        weak_categories = get_parent_categories(weak_subcategories)
        logger.debug(f"Weak categories: {weak_categories}")
        return self._get_questions_for_categories(weak_categories, count)

    def _get_exploring_questions(self, count: int) -> list[Question]:
        chosen_college = User.objects.get(id=self.user_id).chosen_college
        college_name = chosen_college.name if chosen_college else "Outra"

        source_filter = COLLEGE_TO_EXAM.get(college_name, "All")

        return (
            self._get_more_unanswered_questions(count, source__startswith=source_filter)
            if source_filter != "All"
            else self._get_more_unanswered_questions(count)
        )

    def _get_random_questions(self, count: int) -> list[Question]:
        questions = list(
            Question.objects.exclude_inactive()
            .filter_by_type(QuestionType.MULTIPLE_CHOICE)
            .exclude(id__in=self.excluded_ids)
            .order_by("?")[:count]
        )
        logger.debug(f"Retrieved {len(questions)} random questions")
        return questions

    def _get_more_unanswered_questions(self, count: int, **filters) -> list[Question]:
        questions = list(
            Question.objects.exclude_inactive()
            .filter_by_type(QuestionType.MULTIPLE_CHOICE)
            .exclude(id__in=self.excluded_ids)
            .exclude(id__in=self.recently_answered_ids)
            .filter(**filters)
            .order_by("?")[:count]
        )
        logger.debug(f"Retrieved {len(questions)} unanswered questions")
        return questions

    def _get_questions_for_subcategories(
        self, subcategories: set[str], count: int
    ) -> list[Question]:
        return self._get_more_unanswered_questions(count, subcategory__in=subcategories)

    def _get_questions_for_categories(
        self, categories: set[str], count: int
    ) -> list[Question]:
        return self._get_more_unanswered_questions(count, category__in=categories)

    def _get_recently_answered_ids(self) -> set[int]:
        ids = set(
            SessionQuestionUser.objects.filter(user_id=self.user_id)
            .filter_by_type("multiple_choice")
            .order_by("-timestamp")
            .values_list("session_question__question_id", flat=True)[
                :NUM_QUESTIONS_FOR_ALREADY_ANSWERED
            ]
        )
        logger.debug(f"Retrieved {len(ids)} recently answered question IDs")
        return ids

    def _get_parent_related_question_ids(self, parent_quiz_id: int) -> set[int]:
        """Fetch the IDs of questions from the parent quiz and its child quizzes."""
        parent_question_ids = set(
            Question.objects.filter(sessions__id=parent_quiz_id).values_list(
                "id", flat=True
            )
        )
        logger.debug(
            f"Parent quiz {parent_quiz_id} contains {len(parent_question_ids)} questions"
        )

        child_question_ids = set(
            Question.objects.filter(
                sessions__parent_session_id=parent_quiz_id
            ).values_list("id", flat=True)
        )
        logger.debug(
            f"Child quizzes of parent quiz {parent_quiz_id} contain {len(child_question_ids)} questions"
        )

        return parent_question_ids.union(child_question_ids)


def get_total_multiple_choice_questions_per_subcategory():
    return {
        item["subcategory"]: item["total_questions"]
        for item in Question.objects.filter_by_type(QuestionType.MULTIPLE_CHOICE)
        .values("subcategory")
        .annotate(total_questions=Count("id", distinct=True))
        if item["subcategory"]
    }


def get_parent_categories(subcategories: set[str]):
    return set(
        SUBCATEGORIES_TO_PARENT_CATEGORIES.get(subcategory, "")
        for subcategory in subcategories
    )


async def get_questions_text_from_blocks_or_topic(
    question_blocks: list[str],
    topic: str,
    n_questions_per_block: int | None,
    n_questions_for_topic: int | None,
    is_fast: bool,
    subject: str,
) -> list[QuestionInstance]:
    """
    Generate question text from either transcription blocks or a theme.
    Returns a list of QuestionInstance objects.
    """
    all_questions: list[QuestionInstance] = []
    logger.debug(f"Getting questions from blocks: {question_blocks}")

    is_math = subject in ["Matemática", "Física", "Química"]

    if question_blocks:
        # Filter out empty blocks and create tasks for each valid block
        tasks = [
            _generate_question_set_from_description(
                block.strip(), "", n_questions_per_block, is_math
            )
            for block in question_blocks
            if block and block.strip() and n_questions_per_block
        ]

        if tasks:
            # Execute all tasks concurrently
            question_sets = await asyncio.gather(*tasks)
            # Extend all_questions with questions from each set
            for question_set in question_sets:
                all_questions.extend(question_set.questions)
    else:
        if topic.strip() and n_questions_for_topic:
            question_set = await _generate_question_set_from_topic(
                topic.strip(), "", n_questions_for_topic, is_math
            )
            all_questions.extend(question_set.questions)

    logger.debug(f"Got questions from blocks or topic: {all_questions}")
    return all_questions


def create_questions_from_question_instances(
    question_instances: list[QuestionInstance],
) -> list[Question]:
    processed_instances: list[dict[str, str | list[str] | int]] = []
    for q in question_instances:
        original_correct_index = ord(q.correct_choice.upper()) - ord("A")

        if original_correct_index < 0 or original_correct_index > len(q.choices):
            logger.warning(
                f"Invalid correct_choice '{q.correct_choice}' for question: {q.text}"
            )
            continue

        correct_text = q.choices[original_correct_index]

        shuffled_choices = q.choices.copy()
        random.shuffle(shuffled_choices)

        # Find the new index of the correct answer
        new_correct_index = shuffled_choices.index(correct_text)
        new_correct_letter = string.ascii_uppercase[new_correct_index]

        # Create a new instance with shuffled choices
        processed_instance: dict[str, str | list[str] | int] = {
            "text": q.text,
            "choices": shuffled_choices,
            "correct_letter": new_correct_letter,
        }
        processed_instances.append(processed_instance)

    all_questions: list[Question] = []
    all_choices: list[Choice] = []

    with transaction.atomic():
        # Create Question objects
        questions_to_create = [
            Question(
                text=q["text"],
                source=CUSTOM_SOURCE,
                is_active=False,
            )
            for q in processed_instances
        ]
        created_questions = Question.objects.bulk_create(questions_to_create)
        all_questions.extend(created_questions)

        # Create Choice objects
        for question, q in zip(created_questions, processed_instances):
            choices = [
                Choice(
                    question=question,
                    text=choice_text,
                    is_correct=(string.ascii_uppercase[i] == q["correct_letter"]),
                    _order=i,
                )
                for i, choice_text in enumerate(q["choices"])
            ]
            all_choices.extend(choices)

        if all_choices:
            Choice.objects.bulk_create(all_choices)

    return all_questions


def _delatexify_question_set(question_set: QuestionSet) -> list[QuestionInstance]:
    """Convert LaTeX in questions to plain text."""
    delatexified_questions: list[QuestionInstance] = []
    for question in question_set.questions:
        delatexified_question = QuestionInstance(
            text=LatexNodes2Text().latex_to_text(question.text),
            choices=[
                LatexNodes2Text().latex_to_text(choice) for choice in question.choices
            ],
            correct_choice=question.correct_choice,
        )
        delatexified_questions.append(delatexified_question)
    return delatexified_questions


async def _generate_question_set_from_description(
    description: str, extra_instructions: str, num_questions: int, is_math: bool
) -> QuestionSet:
    if not is_math:
        # Regular non-math question generation
        user_message = (
            f"Com base no seguinte conteúdo, gere {num_questions} questões:\n\n"
            f"Descrição: {description}\n\n"
        )

        if extra_instructions:
            user_message += f"\nInstruções extras: {extra_instructions}"

        return (
            await openai_utils.aget_completion_parsed(
                model="gpt-4o",
                temperature=0.5,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION,
                    },
                    {"role": "user", "content": user_message},
                ],
                response_format=QuestionSet,
                timeout=60,
            )
        ).content
    else:
        # Math question generation using o3-mini model
        user_message = (
            f"Com base no seguinte conteúdo, gere {num_questions} questões:\n\n"
            f"Descrição:\n{description}"
        )

        if extra_instructions:
            user_message += f"\nInstruções extras: {extra_instructions}"

        response = await openai_utils.aget_completion_parsed(
            model="o3-mini",
            messages=[
                {
                    "role": "system",
                    "content": USER_MESSAGE_QUESTION_GENERATION_DESCRIPTION_MATH,
                },
                {"role": "user", "content": user_message},
            ],
            response_format=QuestionSet,
            reasoning_effort="high",
            timeout=90,
        )

        # Retorna o conteúdo analisado e os tokens utilizados
        question_set = response.content
        tokens_used = response.tokens_used
        logger.info(f"Tokens used: {tokens_used}")

        return QuestionSet(questions=_delatexify_question_set(question_set))


async def _generate_question_set_from_topic(
    topic: str, extra_instructions: str, num_questions: int, is_math: bool
) -> QuestionSet:
    if not is_math:
        # Regular non-math question generation
        user_message = (
            f"Com base no seguinte tema, gere {num_questions} questões:\n\n"
            f"Tema: {topic}\n\n"
        )

        if extra_instructions:
            user_message += f"\nInstruções extras: {extra_instructions}"

        response = await openai_utils.aget_completion_parsed(
            model="gpt-4o",
            temperature=0.5,
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE_QUESTION_GENERATION_THEME},
                {"role": "user", "content": user_message},
            ],
            response_format=QuestionSet,
            timeout=90,
        )
        logger.info(f"Tokens used: {response.tokens_used}")
        return response.content
    else:
        user_message = (
            f"Com base no seguinte tema, gere {num_questions} questões:\n\n"
            f"Tema:\n{topic}"
        )

        response = await openai_utils.aget_completion_parsed(
            model="o3-mini",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_MESSAGE_QUESTION_GENERATION_THEME_MATH,
                },
                {"role": "user", "content": user_message},
            ],
            response_format=QuestionSet,  # Especifica o formato de resposta esperado
            reasoning_effort="high",
            timeout=90,
        )

    # Retorna o conteúdo analisado e os tokens utilizados
    question_set = response.content
    tokens_used = response.tokens_used
    logger.info(f"Tokens used: {tokens_used}")

    return QuestionSet(questions=_delatexify_question_set(question_set))


async def new_generate_transcriptions(
    files: list[UploadedFile],
    session_id: str,
) -> None:
    """
    Receives images or PDFs; images go to S3 + gpt-4.1-nano, PDFs go directly
    to Gemini 2.5 Flash Preview (bytes inline or File API).
    """
    if not files:
        raise ValueError("Envie pelo menos um arquivo de imagem ou PDF.")

    if not all(f.content_type in VALID_MIME_TYPES_FOR_TRANSCRIPTION for f in files):
        raise ValueError("Formatos permitidos: JPEG, PNG, JPG e PDF.")

    images = [f for f in files if f.content_type != "application/pdf"]
    pdfs = [f for f in files if f.content_type == "application/pdf"]
    if images and pdfs:
        raise ValueError("Envie apenas imagens OU apenas PDFs por chamada.")

    transcripts: list[str]

    # ---------------- IMAGES -------------------------------------------------
    if images:
        # 1) upload to S3
        urls = await asyncio.gather(
            *(file_utils.upload_file_as_temp(f) for f in images)
        )
        # 2) gpt-4.1-nano
        transcripts = await asyncio.gather(
            *(openai_utils.transcribe_image(u) for u in urls)
        )

    # ---------------- PDFs ----------------------------------------------------
    else:
        pdf_async = sync_to_async(
            gemini_utils.transcribe_uploaded_pdf, thread_sensitive=False
        )
        transcripts = await asyncio.gather(*(pdf_async(f) for f in pdfs))

    # transcripts -> list of strings
    cleaned: list[str] = [
        LatexNodes2Text().latex_to_text(t).strip() for t in transcripts if t
    ]

    # Join all transcripts into a single text
    big_text = " ".join(cleaned)

    # Use the split_text_into_chunks function from ai_utils
    blocks = ai_utils.split_text_into_chunks(big_text, TOKENS_PER_BLOCK)

    if not blocks:
        raise ValueError("Falha ao gerar transcrições.")

    objs = [
        Transcription(
            session_id=session_id,
            block_number=idx + 1,
            block_text=block,
            title="",  # vazio por enquanto
        )
        for idx, block in enumerate(blocks)
    ]
    await Transcription.objects.abulk_create(objs)

    logger.info(f"Created {len(objs)} transcriptions for session {session_id}")

    return None
