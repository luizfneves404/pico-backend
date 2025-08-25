"""
FastAPI question service for flow management.
This module provides complete FastAPI implementations for question generation,
transcription processing, and official question retrieval.
"""

import asyncio
import base64
import io
import logging
import random
from collections import Counter
from typing import Any, Coroutine, TypedDict, cast

from fastapi import UploadFile
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pylatexenc.latex2text import LatexNodes2Text
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.datastructures import Headers

from app.arq_client import enqueue_job
from app.database import db_manager
from app.files.models import File
from app.files.service import create_file
from app.flows.constants import (
    PROMPT_COVER_GENERATION,
    SYSTEM_MESSAGE_BLOCK_TITLE,
    SYSTEM_MESSAGE_CHECK_MATH_INVOLVEMENT,
    SYSTEM_MESSAGE_CLASSIFY_TOPIC_SUBJECT,
    SYSTEM_MESSAGE_GENERATE_MINOR_TAGS_FOR_TOPIC,
    SYSTEM_MESSAGE_GENERATE_TITLE_FROM_TRANSCRIPTIONS,
    SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION,
    SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION_MATH,
    SYSTEM_MESSAGE_QUESTION_GENERATION_THEME,
    SYSTEM_MESSAGE_QUESTION_GENERATION_THEME_MATH,
    SYSTEM_MESSAGE_QUESTION_PERTINENCE_TO_TOPIC,
    QuestionInstance,
    QuestionSet,
)
from app.flows.db_types import RichText, TextBlock
from app.flows.models import (
    ENEM_AREAS,
    Choice,
    Exam,
    Flow,
    FlowElement,
    FlowQuestion,
    FlowTranscriptionBlock,
    OfficialQuestionSource,
    Question,
    QuestionAnswerType,
    QuestionArea,
    QuestionDifficulty,
    QuestionSourceType,
)
from app.flows.schemas import PromptType
from app.shared import ai_utils, gemini_utils, openai_utils

logger = logging.getLogger(__name__)
TOKENS_PER_BLOCK = 300


# Constants
DAYS_AGO_TO_EXCLUDE_RECENT_ANSWERS = 7
TOP_TAGS_COUNT = 10  # Number of most frequent tags to save to flow.minor_tags

VALID_MIME_TYPES_FOR_TRANSCRIPTION = [
    "image/jpeg",
    "image/png",
    "image/jpg",
    "application/pdf",
]


class QuestionAreaNotFoundError(Exception):
    """Raised when a question area is not found"""

    pass


class FlowNotFoundError(Exception):
    """Raised when a flow is not found"""

    pass


def latex_to_text(latex: str) -> str:
    """Convert LaTeX to text. Passes through to pylatexenc, but with type hints."""
    return cast(str, LatexNodes2Text().latex_to_text(latex))


async def _get_existing_questions_for_prompt(
    db_session: AsyncSession, flow_id: int
) -> str:
    """
    Get existing questions in the flow to provide context for AI generation.
    Returns a formatted string with existing question texts.
    """
    try:
        query = (
            select(Question.content_blocks)
            .join(FlowElement, Question.id == FlowElement.question_id)
            .where(
                FlowElement.flow_id == flow_id,
                Question.source_type == QuestionSourceType.AI_GENERATED,
            )
            .limit(10)  # Limit to avoid too much context
        )

        result = await db_session.execute(query)
        content_blocks_list = result.scalars().all()

        if not content_blocks_list:
            return ""

        question_texts: list[str] = []
        for content_blocks in content_blocks_list:
            # Extract text from content blocks - handle both dict and object format
            for block in content_blocks:
                if hasattr(block, "block_type") and block.block_type == "text":
                    # Handle TextBlock object
                    if hasattr(block, "content") and block.content:
                        for rich_text in block.content:
                            if hasattr(rich_text, "text"):
                                question_texts.append(rich_text.text)
                elif isinstance(block, dict) and block.get("type") == "text":
                    # Handle dict format
                    question_texts.append(block.get("text", ""))

        return "\n".join(question_texts[:10])  # Limit to 10 questions
    except Exception as e:
        logger.error(f"Error getting existing questions for flow {flow_id}: {str(e)}")
        return ""


async def get_official_questions(
    db_session: AsyncSession,
    *,
    n_questions: int,
    embedding: list[float] | None,
    question_area_name: str | None,
    exam_id: int | None,
    exam_country_code: str | None,
    exam_education_level_id: int | None,
    source_year: int | None,
    question_type: QuestionAnswerType,
    difficulty: QuestionDifficulty | None,
    exclude_question_ids: set[int] = set(),
) -> list[Question]:
    """Get official questions.
    As a rule of thumb, if you pass a falsy value, the filter is not applied.

    Args:
        db_session (AsyncSession): Database session
        n_questions (int): Number of questions to get
        embedding (list[float] | None): Embedding that should be used to order the questions that pass the filters
        question_area_name (str | None): Filter by question area name
        exam_id (int | None): Filter by exam ID
        exam_country_code (str | None): Filter by exam country code
        exam_education_level_id (int | None): Filter by exam education level ID
        source_year (int | None): Filter by source year (exam year)
        question_type (QuestionAnswerType): Filter by question type (multiple choice or open-ended)
        difficulty (QuestionDifficulty | None): Filter by difficulty
        exclude_question_ids (set[int], optional): question IDs to guarantee will be excluded from the result. Defaults to set().

    Raises:
        QuestionAreaNotFoundError: Raised when a question area is not found

    Returns:
        list[Question]: List of questions gotten from the database
    """
    logger.info(f"Getting {n_questions} official questions with filters")

    # Base query
    query = select(Question).where(
        Question.source_type == QuestionSourceType.OFFICIAL,
        Question.is_active.is_(True),
        Question.answer_type == question_type,
    )

    query = query.join(OfficialQuestionSource, Question.official_source).join(
        Exam, OfficialQuestionSource.exam
    )

    # Apply area filter
    if question_area_name:
        area = await db_session.scalar(
            select(QuestionArea).where(QuestionArea.name == question_area_name)
        )
        if area is None:
            raise QuestionAreaNotFoundError(
                f"Área de questão '{question_area_name}' inexistente"
            )
        query = query.where(Question.major_tags.overlap(area.tags))

    # Exam-specific filters
    if exam_id:
        query = query.where(OfficialQuestionSource.exam_id == exam_id)
    if exam_country_code:
        query = query.where(Exam.country.has(code=exam_country_code))
    if exam_education_level_id:
        query = query.where(Exam.education_level_id == exam_education_level_id)
    if source_year:
        query = query.where(OfficialQuestionSource.year == source_year)

    # Difficulty and exclusion
    if difficulty:
        query = query.where(Question.difficulty == difficulty)
    if exclude_question_ids:
        query = query.where(~Question.id.in_(exclude_question_ids))

    # Ordering
    if embedding:
        query = query.order_by(Question.embedding.cosine_distance(embedding))
    else:
        query = query.order_by(func.random())

    # Privileged mix
    if not exam_id:
        privileged_count = int(n_questions * 0.6)
        regular_count = n_questions - privileged_count

        privileged_q = query.where(Exam.is_privileged.is_(True)).limit(privileged_count)
        priv_res = await db_session.scalars(privileged_q)
        priv_questions = list(priv_res)

        excl_ids = set(q.id for q in priv_questions)
        if exclude_question_ids:
            excl_ids |= exclude_question_ids

        remaining_q = query.where(~Question.id.in_(excl_ids)).limit(regular_count)
        rem_res = await db_session.scalars(remaining_q)
        rem_questions = list(rem_res)

        questions = priv_questions + rem_questions
    else:
        result = await db_session.scalars(query.limit(n_questions))
        questions = list(result)

    logger.info(f"Found {len(questions)} official questions")
    return questions


async def task_generate_transcriptions(
    ctx: dict[str, Any],
    file_ids: list[
        int
    ],  # List of File ids for File objects already persisted to storage
    flow_id: int,
    user_id: int,
) -> None:
    """
    Recebe uma lista de objetos File já persistidos no storage, gera transcrições, particiona
    em blocos de até `TOKENS_PER_BLOCK` tokens, atribui títulos e grava
    em `flow_transcription_blocks`.

    Esta função resolve problemas de arquivos fechados e uso de memória ao trabalhar
    com arquivos já persistidos no storage.
    """

    # --------- 1. Initial checks --------------------------------------
    if not file_ids:
        raise ValueError("Envie pelo menos um arquivo.")

    flow_title: str | None = None

    # --------- FIRST OPERATION: Transcriptions and mark as ready ---------
    async with db_manager.session_with_transaction() as db_session:
        files = (
            await db_session.scalars(select(File).where(File.id.in_(file_ids)))
        ).all()
        # Separate files by type using the original name
        images = [
            f
            for f in files
            if f.original_name.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        pdfs = [f for f in files if f.original_name.lower().endswith(".pdf")]

        if images and pdfs:
            raise ValueError("Envie apenas imagens OU apenas PDFs por chamada.")

        # --------- 2. Transcription ------------------------------------------------
        transcripts: list[str]

        if images:
            # For images: use direct URLs for transcription via OpenAI
            try:
                logger.info(
                    f"Flow {flow_id}: transcrevendo {len(images)} imagens via URLs"
                )

                urls = await asyncio.gather(
                    *(file_obj.get_url() for file_obj in images)
                )

                transcripts = await asyncio.gather(
                    *(openai_utils.transcribe_image(url) for url in urls)
                )

            except Exception:
                logger.exception("Falha na transcrição das imagens")
                raise

        else:  # PDFs
            # For PDFs: use file streams to avoid loading everything into memory
            try:
                logger.info(
                    f"Flow {flow_id}: transcrevendo {len(pdfs)} PDFs via file streams"
                )

                async def transcribe_pdf_from_file(pdf_file: File) -> str:
                    async with pdf_file.get_file_like() as file_like:
                        return await gemini_utils.transcribe_uploaded_pdf(file_like)

                transcripts = await asyncio.gather(
                    *(transcribe_pdf_from_file(pdf) for pdf in pdfs)
                )

            except Exception:
                logger.exception("Falha na transcrição dos PDFs")
                raise

        # --------- 3. Post-processing -----------------------------------------
        cleaned = [latex_to_text(t).strip() for t in transcripts if t and t.strip()]
        big_text = " ".join(cleaned)

        block_texts = ai_utils.split_text_into_chunks(
            big_text, TOKENS_PER_BLOCK, "gpt-5-nano"
        )
        if not block_texts:
            raise ValueError("Falha ao gerar transcrições.")

        logger.info(f"Flow {flow_id}: block_texts: {block_texts}")

        # --------- 4. Title generation ----------------------------------------
        block_titles = await asyncio.gather(
            *(_generate_block_title(txt) for txt in block_texts)
        )
        logger.info(f"Flow {flow_id}: block_titles: {block_titles}")

        requires_math = await check_if_titles_involve_math_calculations(block_titles)
        if requires_math:
            logger.info(f"Flow {flow_id} requires math")

        flow = await db_session.scalar(select(Flow).where(Flow.id == flow_id))
        if not flow:
            raise FlowNotFoundError()

        final_title = await generate_flow_title_from_block_titles(block_titles)
        if final_title:
            logger.info(f"Final title for flow {flow_id}: {final_title}")

        flow.has_quantitative_questions = requires_math
        flow.title = final_title
        db_session.add(flow)
        await db_session.flush()

        # --------- 5. Persistence ----------------------------------------------
        blocks = [
            FlowTranscriptionBlock(
                flow_id=flow_id,
                block_number=idx + 1,
                block_text=txt,
                title=title,
            )
            for idx, (txt, title) in enumerate(zip(block_texts, block_titles))
        ]
        db_session.add_all(blocks)

        # Mark flow as ready after transcription is complete
        flow.is_ready = True
        db_session.add(flow)

        # Store the title for cover image generation
        flow_title = flow.title

    logger.info(f"Created {len(blocks)} transcription blocks for flow {flow_id}")
    logger.info(f"Flow {flow_id} marked as ready")

    # --------- SECOND OPERATION: Generate cover image -------------------------
    # This operation happens AFTER the transcriptions are committed
    if flow_title:
        try:
            async with db_manager.session_with_transaction() as db_session:
                cover_image_base64 = await generate_flow_cover_image(flow_title)

                if cover_image_base64:
                    file_id = await save_cover_image_to_flow(
                        db_session, flow_id, cover_image_base64
                    )

                    if file_id:
                        logger.info(
                            f"Generated and saved cover image for flow {flow_id}, file_id: {file_id}"
                        )
                    else:
                        logger.warning(f"Failed to save cover image for flow {flow_id}")
                else:
                    logger.warning(f"Failed to generate cover image for flow {flow_id}")

        except Exception as e:
            # Log error but don't fail the entire operation since transcriptions are already done
            logger.error(f"Failed to generate cover image for flow {flow_id}: {str(e)}")


async def generate_flow_cover_image(flow_title: str) -> str:
    """
    Generate a cover image for a flow returning base64 data.
    """
    logger.info(f"Generating cover image for flow {flow_title}")
    prompt = PROMPT_COVER_GENERATION.format(flow_title=flow_title)
    image_base64 = await openai_utils.generate_image(prompt, format="jpeg", model="gpt-image-1")
    if image_base64:
        logger.info(
            f"Successfully generated cover image for flow {flow_title}: {len(image_base64)} chars"
        )
    else:
        logger.warning(f"Failed to generate cover image for flow {flow_title}")
    return image_base64


async def save_cover_image_to_flow(
    db_session: AsyncSession, flow_id: int, image_base64: str
) -> int | None:
    """
    Save cover image from base64 data to flow.

    Args:
        db_session: Database session
        flow_id: ID of the flow to update
        image_base64: Base64 encoded image data

    Returns:
        The ID of the created File object, or None if failed
    """
    logger.info(f"Preparing to save cover image for flow {flow_id}")

    try:
        image_data = base64.b64decode(image_base64)
    except Exception as e:
        logger.error(f"Failed to decode base64 image for flow {flow_id}: {str(e)}")
        return None

    # Create file-like object in memory
    image_buffer = io.BytesIO(image_data)
    filename = f"flow_cover_{flow_id}.jpg"

    headers = Headers({"content-type": "image/jpeg"})
    upload_file = UploadFile(
        file=image_buffer,
        filename=filename,
        size=len(image_data),
        headers=headers,
    )

    # Save to storage and database
    file_obj = await create_file(db_session, upload_file)
    await db_session.flush()

    # Update flow with cover image
    flow = await db_session.scalar(select(Flow).where(Flow.id == flow_id))
    if flow:
        flow.cover_image_id = file_obj.id
        db_session.add(flow)
        await db_session.flush()

    logger.info(f"Saved cover image for flow {flow_id}, file_id: {file_obj.id}")
    return file_obj.id


#! Exclusively for create_flow_with_optional_files on flow_service.py
# TODO: Move back to flow_service.py: currently here to avoid circular imports of generate_flow_cover_image -> Create new file for such funtions
async def task_generate_flow_cover_image(
    ctx: dict[str, Any],
    flow_id: int,
    flow_title: str,
) -> None:
    """
    Task to generate cover image for flow in background.
    This task is executed AFTER the transcriptions are committed.
    """
    try:
        logger.info(
            f"Generating cover image for flow {flow_id} with title: {flow_title}"
        )

        cover_image_base64 = await generate_flow_cover_image(flow_title)

        if cover_image_base64:
            async with db_manager.session_with_transaction() as db_session:
                file_id = await save_cover_image_to_flow(
                    db_session, flow_id, cover_image_base64
                )

                if file_id:
                    logger.info(
                        f"Successfully generated and saved cover image for flow {flow_id}, file_id: {file_id}"
                    )
                else:
                    logger.warning(f"Failed to save cover image for flow {flow_id}")
        else:
            logger.warning(f"Failed to generate cover image for flow {flow_id}")

    except Exception as e:
        logger.error(f"Error generating cover image for flow {flow_id}: {str(e)}")
        # Do not propagate error, as it is not a critical operation


async def check_if_titles_involve_math_calculations(block_titles: list[str]) -> bool:
    """
    Check if the block titles involve math calculations using openai.
    """
    messages = [
        {"role": "system", "content": SYSTEM_MESSAGE_CHECK_MATH_INVOLVEMENT},
        {
            "role": "user",
            "content": f"Verifique se os seguintes títulos envolvem cálculos matemáticos: {block_titles}",
        },
    ]
    response = await openai_utils.get_completion(
        model="gpt-5-mini",
        temperature=None,
        messages=cast(list[ChatCompletionMessageParam], messages),
        json_mode=False,
        timeout=30,
        reasoning_effort="medium",
    )

    return response.content.strip().upper() == "SIM"


async def generate_tags_for_topic(topic: str) -> tuple[list[str], list[str]]:
    """
    Generate major and minor tags for a topic using AI.

    Args:
        topic: The topic text to generate tags for

    Returns:
        Tuple containing (major_tags, minor_tags)
    """
    try:
        # Generate major tag (subject classification) using ENEM_AREAS approach
        major_tag = await _classify_topic_subject(topic)

        # Generate minor tags (specific topics)
        minor_tags_response = await openai_utils.get_completion(
            model="gpt-5-mini",
            temperature=None,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_MESSAGE_GENERATE_MINOR_TAGS_FOR_TOPIC,
                },
                {"role": "user", "content": f"Tópico: {topic}"},
            ],
            json_mode=False,
            timeout=30,
            reasoning_effort="medium",
        )

        minor_tags_text = minor_tags_response.content.strip()
        minor_tags = [tag.strip() for tag in minor_tags_text.split(",") if tag.strip()]

        return [major_tag] if major_tag else [], minor_tags[:5]  # Limit to 5 minor tags

    except Exception as e:
        logger.error(f"Error generating tags for topic '{topic}': {str(e)}")
        return [], []


async def _classify_topic_subject(topic: str) -> str:
    """
    Classify topic to determine major tag (subject).
    Uses all subjects from ENEM_AREAS at once.
    """
    try:
        # Get all subjects from ENEM_AREAS
        all_subjects = sum(ENEM_AREAS.values(), [])
        system_message = SYSTEM_MESSAGE_CLASSIFY_TOPIC_SUBJECT.format(
            subjects=chr(10).join(all_subjects)
        )

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"Tópico: {topic}"},
        ]

        response = await openai_utils.get_completion(
            model="gpt-5-mini",
            temperature=None,
            messages=messages,
            timeout=30,
            reasoning_effort="medium",
        )

        response_text = response.content.strip()
        if response_text in all_subjects:
            return response_text

        # Final fallback
        return "Conhecimentos Gerais"

    except Exception as e:
        logger.error(f"Error classifying topic subject for '{topic}': {str(e)}")
        return "Conhecimentos Gerais"


async def get_topic_user_generated_questions(
    db_session: AsyncSession,
    *,
    flow: Flow,
    n_questions: int,
    prompt_type: PromptType,
    extra_instructions: str,
    requires_math: bool,
) -> list[Question]:
    """
    Generate AI questions based on a topic for a flow.
    """
    model = "gpt-5" 
    reasoning_models = ["gpt-5"]

    logger.info(
        f"Generating {n_questions} AI questions for flow {flow.id} with topic: {flow.input_topic}"
    )

    # Generate tags for the flow topic and assign to flow
    if flow.input_topic:
        major_tags, minor_tags = await generate_tags_for_topic(flow.input_topic)
        flow.major_tags = major_tags
        flow.minor_tags = minor_tags
        db_session.add(flow)
        await db_session.flush()
        logger.info(
            f"Generated tags for flow {flow.id}: major={major_tags}, minor={minor_tags}"
        )

    system_message = (
        SYSTEM_MESSAGE_QUESTION_GENERATION_THEME_MATH
        if requires_math
        else SYSTEM_MESSAGE_QUESTION_GENERATION_THEME
    )
    user_message = f"Crie {n_questions} questões sobre: {flow.input_topic}"

    if extra_instructions:
        user_message += f"\n\nInstruções adicionais: {extra_instructions}"

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]
    response = await openai_utils.get_completion_parsed(
        model=model,
        messages=messages,
        response_format=QuestionSet,
        temperature=None,
        reasoning_effort="medium",
        timeout=90,
    )

    questions_data = response.content

    questions: list[Question] = []
    for question_data in questions_data.questions:
        # Apply delatexify for math subjects
        question_text = question_data.text
        if requires_math:
            question_text = latex_to_text(question_text)

        text_block = TextBlock(
            block_type="text",
            style="paragraph",
            content=[
                RichText(
                    text=question_text,
                    bold=False,
                    italic=False,
                    underline=False,
                    strikethrough=False,
                    link=None,
                )
            ],
        )
        question = Question(
            is_active=False,
            content_blocks=[text_block],
            is_quantitative=requires_math,
            answer_type=QuestionAnswerType.MULTIPLE_CHOICE,
            source_type=QuestionSourceType.AI_GENERATED,
            source_user_id=flow.created_by_id,
            difficulty=QuestionDifficulty.MEDIUM,
            major_tags=[],
            minor_tags=[],
            answer_content_blocks=[],
        )
        db_session.add(question)
        await db_session.flush()

        choices: list[Choice] = []
        correct_choice_letter = question_data.correct_choice  # "A", "B", "C", "D"
        correct_choice_index = ord(correct_choice_letter.upper()) - ord(
            "A"
        )  # Converte para 0, 1, 2, 3

        # Create list of choice data with correctness flags
        class ChoiceData(TypedDict):
            text: str
            is_correct: bool
            original_order: int

        choice_data_list: list[ChoiceData] = []
        for choice_order, choice_text in enumerate(question_data.choices):
            # Apply delatexify for math subjects
            delatexified_choice_text = choice_text
            if requires_math:
                delatexified_choice_text = latex_to_text(choice_text)

            is_correct = choice_order == correct_choice_index
            choice_data_list.append(
                {
                    "text": delatexified_choice_text,
                    "is_correct": is_correct,
                    "original_order": choice_order,
                }
            )

        # Shuffle the choices to randomize the order
        random.shuffle(choice_data_list)

        # Create Choice objects with the new shuffled order
        for new_order, choice_data in enumerate(choice_data_list):
            choice = Choice(
                question_id=question.id,
                text=choice_data["text"],
                is_correct=choice_data["is_correct"],
                order=new_order,
            )
            choices.append(choice)

        db_session.add_all(choices)

        logger.info(
            f"Flow {flow.id}: Created {len(choices)} choices for question {question.id}"
        )

        questions.append(question)

        flow.max_num_questions = n_questions
        db_session.add(flow)
        await db_session.flush()

    logger.info(
        f"Successfully generated {len(questions)} AI questions for flow {flow.id}"
    )
    return questions


async def get_files_user_generated_questions(
    db_session: AsyncSession,
    *,
    flow: Flow,
    n_questions: int,
    prompt_type: PromptType,
    extra_instructions: str,
    requires_math: bool,
) -> list[Question]:
    """
    Generate AI questions based on uploaded files for a flow.
    """
    model = "gpt-5" 
    reasoning_models = ["gpt-5"]

    query = (
        select(FlowTranscriptionBlock)
        .where(FlowTranscriptionBlock.flow_id == flow.id)
        .order_by(FlowTranscriptionBlock.block_number)
    )

    result = await db_session.execute(query)
    transcription_blocks = result.scalars().all()

    if not transcription_blocks:
        logger.warning(f"No transcription blocks found for flow {flow.id}")
        return []

    max_num_questions = n_questions * len(transcription_blocks)
    flow.max_num_questions = max_num_questions
    db_session.add(flow)
    await db_session.flush()

    logger.info(f"generating max_num_questions: {max_num_questions} for flow {flow.id}")

    class BlockQuestion(TypedDict):
        question_data: QuestionInstance
        question_text: str

    # Create tasks for parallel processing of each block
    async def process_block(
        block: FlowTranscriptionBlock, block_index: int
    ) -> list[BlockQuestion]:
        """Process a single block and return its questions"""
        block_text = block.block_text

        if not block_text.strip():
            logger.warning(f"Block {block_index + 1} is empty, skipping")
            return []

        system_message = (
            SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION_MATH
            if requires_math
            else SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION
        )
        # Create user message for this specific block
        user_message = f"Com base no seguinte conteúdo, crie {n_questions} questões:\n\n{block_text}"

        if extra_instructions:
            user_message += f"\n\nInstruções adicionais: {extra_instructions}"

        messages: list[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": system_message,
            },
            {"role": "user", "content": user_message},
        ]

        try:
            response = await openai_utils.get_completion_parsed(
                model=model,
                messages=messages,
                response_format=QuestionSet,
                temperature=None,
                reasoning_effort="medium",
                timeout=90,
            )

            questions_data = response.content
            block_questions: list[BlockQuestion] = []

            for question_data in questions_data.questions:
                # Apply delatexify for math subjects
                question_text = question_data.text
                if requires_math:
                    question_text = latex_to_text(question_text)

                # Create question dict with all necessary data
                question_dict: BlockQuestion = {
                    "question_data": question_data,
                    "question_text": question_text,
                }
                block_questions.append(question_dict)

            return block_questions

        except Exception as e:
            logger.error(
                f"Error generating questions for block {block_index + 1}: {str(e)}"
            )
            return []

    # Execute all block processing tasks in parallel
    tasks: list[Coroutine[Any, Any, list[BlockQuestion]]] = [
        process_block(block, i) for i, block in enumerate(transcription_blocks)
    ]
    block_results: list[list[BlockQuestion] | BaseException] = await asyncio.gather(
        *tasks, return_exceptions=True
    )

    # First pass: Create all questions and choices without tags
    all_questions: list[Question] = []

    for block_index, block_questions in enumerate(block_results):
        if isinstance(block_questions, BaseException):
            logger.error(f"Exception in block {block_index + 1}: {block_questions}")
            continue
        else:
            for block_question in block_questions:
                question_data = block_question["question_data"]
                question_text = block_question["question_text"]

                text_block = TextBlock(
                    block_type="text",
                    style="paragraph",
                    content=[
                        RichText(
                            text=question_text,
                            bold=False,
                            italic=False,
                            underline=False,
                            strikethrough=False,
                            link=None,
                        )
                    ],
                )
                question = Question(
                    is_active=False,
                    content_blocks=[text_block],
                    is_quantitative=requires_math,
                    answer_type=QuestionAnswerType.MULTIPLE_CHOICE,
                    source_type=QuestionSourceType.AI_GENERATED,
                    source_user_id=flow.created_by_id,
                    difficulty=QuestionDifficulty.MEDIUM,
                    major_tags=[],
                    minor_tags=[],
                    answer_content_blocks=[],
                )
                db_session.add(question)
                await db_session.flush()

                choices: list[Choice] = []
                correct_choice_letter = (
                    question_data.correct_choice
                )  # "A", "B", "C", "D"
                correct_choice_index = ord(correct_choice_letter.upper()) - ord("A")

                # Create list of choice data with correctness flags
                class ChoiceData(TypedDict):
                    text: str
                    is_correct: bool
                    original_order: int

                choice_data_list: list[ChoiceData] = []
                for choice_order, choice_text in enumerate(question_data.choices):
                    # Apply delatexify for math subjects
                    delatexified_choice_text = choice_text
                    if requires_math:
                        delatexified_choice_text = latex_to_text(choice_text)

                    is_correct = choice_order == correct_choice_index
                    choice_data_list.append(
                        {
                            "text": delatexified_choice_text,
                            "is_correct": is_correct,
                            "original_order": choice_order,
                        }
                    )

                # Shuffle the choices to randomize the order
                random.shuffle(choice_data_list)

                for new_order, choice_data in enumerate(choice_data_list):
                    choice = Choice(
                        question_id=question.id,
                        text=choice_data["text"],
                        is_correct=choice_data["is_correct"],
                        order=new_order,
                    )
                    choices.append(choice)

                db_session.add_all(choices)
                await db_session.flush()  # Flush to ensure choices are saved

                logger.info(
                    f"Flow {flow.id}: Created {len(choices)} choices for question {question.id}"
                )

                all_questions.append(question)

        # Enqueue background task for tag generation if we have questions
    if all_questions:
        question_ids = [q.id for q in all_questions]

        # Enqueue orchestrator task that ensures proper sequencing
        await enqueue_job(
            "task_generate_and_consolidate_tags",
            question_ids=question_ids,
            flow_id=flow.id,
        )

        logger.info(
            f"Enqueued tag generation orchestrator task for {len(all_questions)} questions in flow {flow.id}"
        )

    logger.info(
        f"Successfully generated {len(all_questions)} AI questions from files for flow {flow.id}"
    )
    return all_questions


async def get_topic_query_official_questions(
    db_session: AsyncSession,
    *,
    flow: Flow,
    n_questions: int,
    question_area_name: str | None = None,
    exam_id: int | None = None,
    exam_country_code: str | None = None,
    exam_education_level_id: int | None = None,
    source_year: int | None = None,
    question_type: QuestionAnswerType = QuestionAnswerType.MULTIPLE_CHOICE,
) -> list[Question]:
    """
    Get official questions based on topic query for a flow.
    Verifies question pertinence and removes questions with score < 3.
    """
    logger.info(
        f"Getting {n_questions} official questions for flow {flow.id} based on topic"
    )

    # Create embedding for the topic
    embedding: list[float] | None = None
    if flow.input_topic:
        embedding = await openai_utils.compute_embedding(flow.input_topic)

    # Get more questions initially to account for filtering
    initial_n_questions = min(
        n_questions * 2, 100
    )  # Cap at 100 to avoid excessive queries

    # Use the generalized function
    questions = await get_official_questions(
        db_session=db_session,
        n_questions=initial_n_questions,
        question_area_name=question_area_name,
        exam_id=exam_id,
        exam_country_code=exam_country_code,
        exam_education_level_id=exam_education_level_id,
        source_year=source_year,
        question_type=question_type,
        embedding=embedding,
        difficulty=None,
    )

    # Verify question pertinence if we have a topic and questions
    filtered_questions = questions
    if flow.input_topic and questions:
        logger.info(
            f"Verifying pertinence of {len(questions)} questions to topic: {flow.input_topic}"
        )

        # Verify pertinence in parallel using asyncio.gather
        pertinence_tasks = [
            verify_question_pertinence_to_topic(
                db_session, flow.id, question.id, flow.input_topic
            )
            for question in questions
        ]

        pertinence_scores = await asyncio.gather(*pertinence_tasks)

        # Create question-score pairs and filter by score >= 3
        question_score_pairs = [
            (question, score)
            for question, score in zip(questions, pertinence_scores)
            if score >= 3
        ]

        logger.info(
            f"Filtered {len(questions)} questions to {len(question_score_pairs)} with pertinence >= 3"
        )

        # Log score distribution for debugging
        score_counts = Counter(pertinence_scores)
        logger.info(f"Pertinence score distribution: {dict(score_counts)}")

        # Sort by pertinence score in descending order (highest pertinence first)
        question_score_pairs.sort(key=lambda x: x[1], reverse=True)

        # Extract questions in order of highest pertinence
        filtered_questions = [pair[0] for pair in question_score_pairs]

    # Take only the requested number of questions (highest pertinence first)
    final_questions = filtered_questions[:n_questions]

    flow.max_num_questions = n_questions
    db_session.add(flow)
    await db_session.flush()

    logger.info(
        f"Final result: {len(final_questions)} official questions for flow {flow.id}"
    )
    return final_questions


async def get_files_query_official_questions(
    db_session: AsyncSession,
    *,
    flow: Flow,
    n_questions: int,
    question_area_name: str | None = None,
    exam_id: int | None = None,
    exam_country_code: str | None = None,
    exam_education_level_id: int | None = None,
    source_year: int | None = None,
    question_type: QuestionAnswerType = QuestionAnswerType.MULTIPLE_CHOICE,
) -> list[Question]:
    """
    Get official questions based on file content for a flow.
    Uses each transcription block title as a separate query for better relevance.
    Verifies question pertinence and removes questions with score < 3.
    """
    logger.info(
        f"Getting {n_questions} official questions for flow {flow.id} based on files"
    )

    query_transcriptions = (
        select(FlowTranscriptionBlock)
        .where(FlowTranscriptionBlock.flow_id == flow.id)
        .order_by(FlowTranscriptionBlock.block_number)
    )

    result = await db_session.execute(query_transcriptions)
    transcription_blocks = result.scalars().all()

    if not transcription_blocks:
        logger.warning(f"No transcription blocks found for flow {flow.id}")
        return []

    # Extract titles from transcription blocks, filter out empty ones
    block_titles = [
        block.title.strip()
        for block in transcription_blocks
        if block.title and block.title.strip()
    ]

    if not block_titles:
        logger.warning(f"No valid block titles found for flow {flow.id}")
        return []

    max_num_questions = n_questions * len(block_titles)
    flow.max_num_questions = max_num_questions
    db_session.add(flow)
    await db_session.flush()

    logger.info(f"getting max_num_questions: {max_num_questions} for flow {flow.id}")

    # Generate all embeddings in parallel using the list overload
    logger.info(f"Generating embeddings for {len(block_titles)} block titles")
    embeddings = await openai_utils.compute_embedding(block_titles)

    # Phase 2: Get questions sequentially with increased count for filtering
    logger.info("Getting questions sequentially for proper deduplication")

    # Get more questions initially to account for filtering
    initial_n_questions = min(
        n_questions * 2, 50
    )  # Cap per block to avoid excessive queries

    # Track question-to-block-title mapping for pertinence verification
    question_to_block_title: dict[int, str] = {}
    all_questions: list[Question] = []
    unique_question_ids: set[int] = set()

    for i, (block_title, embedding) in enumerate(zip(block_titles, embeddings)):
        # Get questions using the generalized function with proper exclusion
        block_questions = await get_official_questions(
            db_session=db_session,
            n_questions=initial_n_questions,
            question_area_name=question_area_name,
            exam_id=exam_id,
            exam_country_code=exam_country_code,
            exam_education_level_id=exam_education_level_id,
            source_year=source_year,
            question_type=question_type,
            embedding=embedding,
            difficulty=None,
            exclude_question_ids=unique_question_ids,  # Properly exclude previous questions
        )

        # Add unique questions to our list and track their block association
        added_count = 0
        for question in block_questions:
            if question.id not in unique_question_ids:
                all_questions.append(question)
                unique_question_ids.add(question.id)
                question_to_block_title[question.id] = block_title
                added_count += 1

        logger.info(
            f"Block {i + 1} ('{block_title[:50]}...'): {added_count} new questions added (total: {len(all_questions)})"
        )

    # Phase 3: Verify question pertinence using block titles
    if all_questions:
        logger.info(
            f"Verifying pertinence of {len(all_questions)} questions to their respective block titles"
        )

        # Create pertinence verification tasks
        pertinence_tasks = [
            verify_question_pertinence_to_topic(
                db_session, flow.id, question.id, question_to_block_title[question.id]
            )
            for question in all_questions
        ]

        pertinence_scores = await asyncio.gather(*pertinence_tasks)

        # Create question-score pairs and filter by score >= 3
        question_score_pairs = [
            (question, score)
            for question, score in zip(all_questions, pertinence_scores)
            if score >= 3
        ]

        logger.info(
            f"Filtered {len(all_questions)} questions to {len(question_score_pairs)} with pertinence >= 3"
        )

        # Log score distribution for debugging
        score_counts = Counter(pertinence_scores)
        logger.info(f"Pertinence score distribution: {dict(score_counts)}")

        # Sort by pertinence score in descending order (highest pertinence first)
        question_score_pairs.sort(key=lambda x: x[1], reverse=True)

        # Extract questions in order of highest pertinence
        sorted_filtered_questions = [pair[0] for pair in question_score_pairs]

        # Take only the requested number of questions (highest pertinence first)
        final_questions = sorted_filtered_questions[:max_num_questions]

        logger.info(
            f"Selected top {len(final_questions)} questions by pertinence score"
        )
    else:
        final_questions = all_questions

    logger.info(
        f"Final result: {len(final_questions)} official questions for flow {flow.id}"
    )
    return final_questions


async def add_questions_to_flow(
    db_session: AsyncSession,
    flow_id: int,
    questions: list[Question],
    start_order: int,
) -> None:
    """
    Add a list of questions to a flow as FlowQuestion elements.
    """
    logger.info(f"Adding {len(questions)} questions to flow {flow_id}")

    flow_questions: list[FlowQuestion] = []
    for order_offset, question in enumerate(questions):
        # Create FlowQuestion
        flow_question = FlowQuestion(
            flow_id=flow_id,
            order=start_order + order_offset,
            question_id=question.id,
        )
        flow_questions.append(flow_question)

    db_session.add_all(flow_questions)
    await db_session.flush()

    # Debug: Check if choices were created for the questions
    question_ids = [q.id for q in questions]
    if question_ids:
        choices_count_query = select(func.count(Choice.id)).where(
            Choice.question_id.in_(question_ids)
        )
        choices_count_result = await db_session.execute(choices_count_query)
        choices_count = choices_count_result.scalar()
        logger.info(
            f"Flow {flow_id}: Total choices in DB for {len(questions)} questions: {choices_count}"
        )

    logger.info(f"Successfully added {len(flow_questions)} questions to flow {flow_id}")


async def _generate_block_title(block_text: str) -> str:
    """Generate a concise title/query for a transcription block."""
    try:
        response = await openai_utils.get_completion(
            model="gpt-5-mini",
            temperature=None,
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE_BLOCK_TITLE},
                {"role": "user", "content": block_text},
            ],
            json_mode=False,
            timeout=30,
            reasoning_effort="medium",
        )
        return response.content.strip()
    except Exception as e:
        logger.error(f"Error generating block title: {str(e)}")
        # Return a fallback title if generation fails
        return "Conteúdo transcrito"


async def generate_flow_title_from_block_titles(
    block_titles: list[str],
) -> str:
    """Generate a concise title based on transcription titles using AI."""
    if not block_titles:
        return "Material de Estudo"

    # Join titles with line breaks for the prompt
    titles_text = "\n".join(f"- {title}" for title in block_titles if title.strip())

    if not titles_text.strip():
        return "Material de Estudo"

    try:
        result = await openai_utils.get_completion(
            model="gpt-5-mini",
            temperature=None,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_MESSAGE_GENERATE_TITLE_FROM_TRANSCRIPTIONS,
                },
                {
                    "role": "user",
                    "content": f"Títulos das transcrições:\n{titles_text}",
                },
            ],
            reasoning_effort="medium",
        )

        title = result.content.strip()
        # Ensure title is not too long
        if len(title) > 60:
            title = title[:57] + "..."

        return title if title else "Material de Estudo"

    except Exception as e:
        logger.error(f"Error generating title from transcriptions: {e}")
        return "Material de Estudo"


async def verify_question_pertinence_to_topic(
    db_session: AsyncSession,
    flow_id: int,
    question_id: int,
    topic: str,
) -> int:
    """Verify question pertinence to a topic using gpt-5-mini (with vision) on a scale of 0-5"""
    try:
        # Get the question with choices loaded
        question = await db_session.scalar(
            select(Question)
            .where(Question.id == question_id)
            .options(selectinload(Question.choices))
        )

        if not question:
            logger.warning(f"Question {question_id} not found")
            return 0

        question_text_with_choices = question.question_text_with_choices_text

        if not question_text_with_choices:
            logger.warning(f"Question {question_id} has no text or choices")
            return 0

        # Check for images in content blocks
        image_ids: list[int] = []
        for block in question.content_blocks:
            if hasattr(block, "block_type") and block.block_type == "image":
                # Handle ImageBlock object
                if hasattr(block, "image_id"):
                    image_ids.append(block.image_id)
            elif isinstance(block, dict) and block.get("block_type") == "image":
                # Handle dict format
                if "image_id" in block:
                    image_ids.append(block["image_id"])

        # Also check for images in choices
        for choice in question.choices:
            if choice.image_id:
                image_ids.append(choice.image_id)

        # Prepare content parts
        content_parts = [
            f"Topic: {topic}",
            f"Question and Choices: {question_text_with_choices}",
        ]

        # Prepare user message content (text + images if any)
        user_message_content: list[dict[str, Any]] = [
            {"type": "text", "text": "\n\n".join(content_parts)}
        ]

        # Add images if present
        if image_ids:
            # Get image URLs
            image_files = await db_session.scalars(
                select(File).where(File.id.in_(image_ids))
            )
            for image_file in image_files:
                try:
                    url = await image_file.get_url()
                    if url:
                        user_message_content.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": url, "detail": "high"},
                            }
                        )
                except Exception as e:
                    logger.warning(f"Failed to get URL for image {image_file.id}: {e}")

        # Use gpt-5-mini for all cases (supports both text and images)
        messages = [
            {
                "role": "system",
                "content": SYSTEM_MESSAGE_QUESTION_PERTINENCE_TO_TOPIC,
            },
            {
                "role": "user",
                "content": user_message_content,
            },
        ]

        response = await openai_utils.get_completion(
            model="gpt-5-mini",
            temperature=None,
            messages=cast(list[ChatCompletionMessageParam], messages),
            json_mode=False,
            timeout=45,  # Increased timeout for vision capabilities
            reasoning_effort="medium",
        )

        # Extract the numeric score from the response
        score_str = response.content.strip()
        try:
            score = int(score_str)
            # Ensure score is within valid range
            if 0 <= score <= 5:
                return score
            else:
                logger.warning(
                    f"Invalid pertinence score {score} for question {question_id}, flow {flow_id}. Using default score 0."
                )
                return 0
        except ValueError:
            logger.warning(
                f"Could not parse pertinence score '{score_str}' for question {question_id}, flow {flow_id}. Using default score 0."
            )
            return 0

    except Exception as e:
        logger.error(
            f"Error verifying question pertinence for question {question_id}, flow {flow_id}: {e}"
        )
        return 0  # Default to 0 if there's an error





# async def generate_initial_questions_from_topic(
#     db_session: AsyncSession,
#     flow_id: int,
#     topic: str,
#     n_questions: int = 3,
#     model: str = "gpt-4.1-mini",
# ) -> None:
#     """
#     Generate initial questions from a topic and add them to the flow.
#     Only generates questions if the flow allows AI questions.
#     """
#     try:
#         # Check if AI questions are allowed for this flow
#         if not await _check_flow_allows_ai_questions(db_session, flow_id):
#             return

#         logger.info(
#             f"Generating {n_questions} initial questions for flow {flow_id} from topic: {topic}"
#         )

#         # Create user message
#         user_message = f"Crie {n_questions} questões sobre o tópico: {topic}"

#         # Get AI-generated questions using structured output
#         messages = [
#             {"role": "system", "content": SYSTEM_MESSAGE_QUESTION_GENERATION_THEME},
#             {"role": "user", "content": user_message},
#         ]

#         response = await openai_utils.get_completion_parsed(
#             model=model, temperature=0.7, messages=messages, response_format=QuestionSet
#         )

#         questions_data = response.content

#         # Create questions and flow elements
#         flow_questions = []
#         for order, question_data in enumerate(questions_data.questions):
#             # Create Question
#             question = Question(
#                 content_blocks=[{"type": "text", "text": question_data.text}],
#                 subject="",  # Will be determined later
#                 answer_type=QuestionAnswerType.MULTIPLE_CHOICE,
#                 source_type=QuestionSourceType.AI_GENERATED,
#                 source_user_id=None,  # System generated
#                 difficulty=QuestionDifficulty.MEDIUM,  # Default
#             )
#             db_session.add(question)
#             await db_session.flush()  # Get question ID

#             # Create choices
#             choices = []
#             correct_choice_text = question_data.correct_choice
#             for choice_order, choice_text in enumerate(question_data.choices):
#                 choice = Choice(
#                     question_id=question.id,
#                     text=choice_text,
#                     is_correct=(choice_text == correct_choice_text),
#                     order=choice_order,
#                 )
#                 choices.append(choice)

#             db_session.add_all(choices)

#             # Create FlowElement and FlowQuestion
#             flow_element = FlowElement(
#                 flow_id=flow_id,
#                 order=order,
#                 element_type="flow_question",
#                 question_id=question.id,
#             )
#             db_session.add(flow_element)
#             await db_session.flush()

#             flow_question = FlowQuestion(
#                 id=flow_element.id,
#                 flow_id=flow_id,
#                 order=order,
#                 element_type="flow_question",
#                 question_id=question.id,
#             )
#             flow_questions.append(flow_question)

#         await db_session.commit()
#         logger.info(
#             f"Successfully generated {len(flow_questions)} questions for flow {flow_id}"
#         )

#     except Exception as e:
#         logger.error(
#             f"Error generating questions from topic for flow {flow_id}: {str(e)}"
#         )
#         await db_session.rollback()
#         raise


# async def generate_initial_questions_from_files(
#     db_session: AsyncSession,
#     flow_id: int,
#     n_questions: int = 3,
#     model: str = "gpt-4.1-mini",
# ) -> None:
#     """
#     Generate initial questions from flow transcription blocks.
#     Only generates questions if the flow allows AI questions.
#     """
#     try:
#         # Check if AI questions are allowed for this flow
#         if not await _check_flow_allows_ai_questions(db_session, flow_id):
#             return

#         logger.info(
#             f"Generating {n_questions} initial questions for flow {flow_id} from files"
#         )

#         # Get transcription blocks
#         query = (
#             select(FlowTranscriptionBlock)
#             .where(FlowTranscriptionBlock.flow_id == flow_id)
#             .order_by(FlowTranscriptionBlock.block_number)
#         )

#         result = await db_session.execute(query)
#         transcription_blocks = result.scalars().all()

#         if not transcription_blocks:
#             logger.warning(f"No transcription blocks found for flow {flow_id}")
#             return

#         # Generate n_questions for the FIRST transcription block only
#         first_block = transcription_blocks[0]
#         block_text = first_block.block_text

#         # Skip if first block is empty
#         if not block_text.strip():
#             logger.warning(f"First transcription block is empty for flow {flow_id}")
#             return

#         # Truncate block if too long
#         if len(block_text) > MAX_TRANSCRIPTION_LENGTH:
#             block_text = block_text[:MAX_TRANSCRIPTION_LENGTH] + "... [truncated]"

#         # Create user message for the first block
#         user_message = f"Com base no seguinte conteúdo, crie {n_questions} questões:\n\n{block_text}"

#         # Get AI-generated questions using structured output
#         messages = [
#             {
#                 "role": "system",
#                 "content": SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION,
#             },
#             {"role": "user", "content": user_message},
#         ]

#         response = await openai_utils.get_completion_parsed(
#             model=model,
#             temperature=0.7,
#             messages=messages,
#             response_format=QuestionSet,
#         )

#         questions_data = response.content

#         # Create questions and flow elements for the first block
#         flow_questions = []
#         for order, question_data in enumerate(questions_data.questions):
#             # Create Question
#             question = Question(
#                 content_blocks=[{"type": "text", "text": question_data.text}],
#                 subject="",  # Will be determined later
#                 answer_type=QuestionAnswerType.MULTIPLE_CHOICE,
#                 source_type=QuestionSourceType.AI_GENERATED,
#                 source_user_id=None,  # System generated
#                 difficulty=QuestionDifficulty.MEDIUM,  # Default
#             )
#             db_session.add(question)
#             await db_session.flush()  # Get question ID

#             # Create choices
#             choices = []
#             correct_choice_text = question_data.correct_choice
#             for choice_order, choice_text in enumerate(question_data.choices):
#                 choice = Choice(
#                     question_id=question.id,
#                     text=choice_text,
#                     is_correct=(choice_text == correct_choice_text),
#                     order=choice_order,
#                 )
#                 choices.append(choice)

#             db_session.add_all(choices)

#             # Create FlowElement and FlowQuestion
#             flow_element = FlowElement(
#                 flow_id=flow_id,
#                 order=order,
#                 element_type="flow_question",
#                 question_id=question.id,
#             )
#             db_session.add(flow_element)
#             await db_session.flush()

#             flow_question = FlowQuestion(
#                 id=flow_element.id,
#                 flow_id=flow_id,
#                 order=order,
#                 element_type="flow_question",
#                 question_id=question.id,
#             )
#             flow_questions.append(flow_question)

#         await db_session.commit()
#         logger.info(
#             f"Successfully generated {len(flow_questions)} questions from first block for flow {flow_id}"
#         )

#     except Exception as e:
#         logger.error(
#             f"Error generating questions from files for flow {flow_id}: {str(e)}"
#         )
#         await db_session.rollback()
#         raise
