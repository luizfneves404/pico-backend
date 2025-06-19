"""
FastAPI question service for flow management.
This module provides complete FastAPI implementations for question generation,
transcription processing, and official question retrieval.
"""

import asyncio
import logging
import random
from typing import Any, Optional, Union
from fastapi import UploadFile
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import text
from pylatexenc.latex2text import LatexNodes2Text

from app.flows.models import (
    Flow,
    FlowTranscriptionBlock,
    FlowElement,
    FlowQuestion,
    Question,
    Choice,
    QuestionSourceType,
    QuestionDifficulty,
    QuestionAnswerType,
    OfficialQuestionSource,
    Exam,
    QuestionArea,
    ENEM_AREAS,
    SUBJECT_TO_AREA,
    FlowSourceType,
)
from app.flows.schemas import PromptType
from app.users.models import User
from app.shared import openai_utils, ai_utils, gemini_utils
from app.config import settings
from app.files.models import File
from app.files.storage import storage
from app.files.service import create_file
from app.flows.db_types import TextBlock, RichText
from app.database import db_manager

logger = logging.getLogger(__name__)

# Constants
DAYS_AGO_TO_EXCLUDE_RECENT_ANSWERS = 7
PRIVILEGED_SOURCES = [
    "ENEM",
    "ENEM PPL",
    "FUVEST",
    "PUC-Rio",
    "FGV",
    "UNICAMP",
    "UERJ",
]

VALID_MIME_TYPES_FOR_TRANSCRIPTION = [
    "image/jpeg",
    "image/png",
    "image/jpg",
    "application/pdf",
]

TOKENS_PER_BLOCK = 300

# Import constants from flows constants
from app.flows.constants import (
    SYSTEM_MESSAGE_QUESTION_GENERATION_THEME,
    SYSTEM_MESSAGE_QUESTION_GENERATION_THEME_MATH,
    SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION,
    SYSTEM_MESSAGE_QUESTION_GENERATION_DESCRIPTION_MATH,
    SYSTEM_MESSAGE_CHECK_MATH_INVOLVEMENT,
    SYSTEM_MESSAGE_GENERATE_TITLE_FROM_TRANSCRIPTIONS,
    MAX_FILE_SIZE_BYTES,
    SUPPORTED_IMAGE_TYPES,
    SUPPORTED_DOCUMENT_TYPES,
    CHUNK_SIZE,
    MAX_TRANSCRIPTION_LENGTH,
    MAX_COMBINED_TRANSCRIPTION_LENGTH,
    SYSTEM_MESSAGE_BLOCK_TITLE,
    QuestionInstance,
    QuestionSet,
)


class FlowNotFoundError(Exception):
    """Raised when a flow is not found"""

    pass


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

        question_texts = []
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
    n_questions: int,
    question_area_name: str | None = None,
    exam_id: int | None = None,
    exam_country_code: str | None = None,
    exam_education_level_id: int | None = None,
    source_year: int | None = None,
    question_type: QuestionAnswerType = QuestionAnswerType.MULTIPLE_CHOICE,
    difficulty: QuestionDifficulty | None = None,
    embeddings: list[list[float]] | None = None,
    exclude_question_ids: set[int] | None = None,
    ensure_privileged_mix: bool = True,
) -> list[Question]:
    """
    Get official questions based on various filters and criteria.

    Args:
        db_session: Database session
        n_questions: Number of questions to return
        question_area_name: Filter by question area name
        exam_id: Filter by specific exam ID
        exam_country_code: Filter by exam country code
        exam_education_level_id: Filter by exam education level
        source_year: Filter by source year
        question_type: Type of questions (multiple choice or open ended)
        difficulty: Filter by difficulty level
        embeddings: List of embeddings for similarity-based ordering
        exclude_question_ids: Set of question IDs to exclude
        ensure_privileged_mix: Whether to ensure 60% from privileged sources

    Returns:
        List of Question objects matching the criteria
    """
    try:
        logger.info(f"Getting {n_questions} official questions with filters")

        # Build base query
        query = select(Question).where(
            Question.source_type == QuestionSourceType.OFFICIAL,
            Question.is_active == True,
            Question.answer_type == question_type,
        )

        # Add relationship joins if needed
        need_exam_join = any(
            [exam_id, exam_country_code, exam_education_level_id, source_year]
        )

        if need_exam_join:
            query = query.join(Question.official_source).join(
                OfficialQuestionSource.exam
            )

        # Apply filters
        if question_area_name:
            area = await db_session.scalar(
                select(QuestionArea).where(QuestionArea.name == question_area_name)
            )
            if area is None:
                raise ValueError(f"Área de questão '{question_area_name}' inexistente")

            query = query.where(Question.major_tags.overlap(area.tags))

        if exam_id:
            query = query.where(OfficialQuestionSource.exam_id == exam_id)

        if exam_country_code:
            query = query.where(Exam.country.has(code=exam_country_code))

        if exam_education_level_id:
            query = query.where(Exam.education_level_id == exam_education_level_id)

        if source_year:
            query = query.where(OfficialQuestionSource.year == source_year)

        if difficulty:
            query = query.where(Question.difficulty == difficulty)

        if exclude_question_ids:
            query = query.where(~Question.id.in_(exclude_question_ids))

        # Apply ordering
        if embeddings:
            # Use the first embedding for ordering (can be extended to handle multiple)
            embedding = embeddings[0]
            query = query.order_by(Question.embedding.cosine_distance(embedding))
        else:
            # Random order if no embeddings provided
            query = query.order_by(func.random())

        # Handle privileged source mix if requested and no specific exam filter
        if ensure_privileged_mix and not exam_id:
            privileged_count = int(n_questions * 0.6)
            regular_count = n_questions - privileged_count

            # Get privileged questions
            privileged_query = query.where(
                or_(*[Exam.name.like(f"{source}%") for source in PRIVILEGED_SOURCES])
            ).limit(privileged_count)

            privileged_result = await db_session.execute(privileged_query)
            privileged_questions = list(privileged_result.scalars().all())

            # Get remaining questions excluding privileged ones
            privileged_ids = [q.id for q in privileged_questions]
            exclude_ids = set(privileged_ids)
            if exclude_question_ids:
                exclude_ids.update(exclude_question_ids)

            remaining_query = query.where(~Question.id.in_(exclude_ids)).limit(
                regular_count
            )

            remaining_result = await db_session.execute(remaining_query)
            remaining_questions = list(remaining_result.scalars().all())

            questions = privileged_questions + remaining_questions
        else:
            # Just apply limit and execute
            query = query.limit(n_questions)
            result = await db_session.execute(query)
            questions = list(result.scalars().all())

        logger.info(f"Found {len(questions)} official questions")
        return questions

    except Exception as e:
        logger.error(f"Error getting official questions: {str(e)}")
        raise


async def task_generate_transcriptions(
    ctx: dict[str, Any],
    file_ids: list[int],  # List of File objects already persisted to storage
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

    # --------- 1. Validações iniciais --------------------------------------
    if not file_ids:
        raise ValueError("Envie pelo menos um arquivo.")

    async with db_manager.session_with_transaction() as db_session:

        files = (
            await db_session.scalars(select(File).where(File.id.in_(file_ids)))
        ).all()
        # Separar arquivos por tipo usando o nome original
        images = [
            f
            for f in files
            if f.original_name.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        pdfs = [f for f in files if f.original_name.lower().endswith(".pdf")]

        if images and pdfs:
            raise ValueError("Envie apenas imagens OU apenas PDFs por chamada.")

        # --------- 2. Transcrição ------------------------------------------------
        transcripts: list[str]

        if images:
            # Para imagens: usar URLs diretas para transcrição via OpenAI
            try:
                logger.info(
                    f"Flow {flow_id}: transcrevendo {len(images)} imagens via URLs"
                )

                urls = await asyncio.gather(
                    *(file_obj.get_url() for file_obj in images)
                )

                # Transcrever imagens usando OpenAI
                transcripts = await asyncio.gather(
                    *(openai_utils.transcribe_image(url) for url in urls)
                )

            except Exception as e:
                logger.exception("Falha na transcrição das imagens")
                raise

        else:  # PDFs
            # Para PDFs: usar file streams para evitar carregar tudo na memória
            try:
                logger.info(
                    f"Flow {flow_id}: transcrevendo {len(pdfs)} PDFs via file streams"
                )

                async def transcribe_pdf_from_file(pdf_file: File) -> str:
                    async with pdf_file.get_file_like() as file_like:
                        return await gemini_utils.transcribe_uploaded_pdf(file_like)

                # Transcrever PDFs usando file streams
                transcripts = await asyncio.gather(
                    *(transcribe_pdf_from_file(pdf) for pdf in pdfs)
                )

            except Exception as e:
                logger.exception("Falha na transcrição dos PDFs")
                raise

        # --------- 3. Pós‑processamento -----------------------------------------
        cleaned = [
            LatexNodes2Text().latex_to_text(t).strip()
            for t in transcripts
            if t and t.strip()
        ]
        big_text = " ".join(cleaned)

        block_texts = ai_utils.split_text_into_chunks(big_text, TOKENS_PER_BLOCK)
        if not block_texts:
            raise ValueError("Falha ao gerar transcrições.")

        logger.info(f"Flow {flow_id}: block_texts: {block_texts}")

        # --------- 4. Geração de títulos ----------------------------------------
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

        # --------- 5. Persistência ----------------------------------------------
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
        await db_session.commit()

        logger.info(f"Created {len(blocks)} transcription blocks for flow {flow_id}")


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
        model="gpt-4.1-nano",
        temperature=0.2,
        messages=messages,
        json_mode=False,
        timeout=15,
    )

    return response.content.strip().upper() == "SIM"


async def get_topic_user_generated_questions(
    db_session: AsyncSession,
    flow: Flow,
    n_questions: int,
    prompt_type: PromptType,
    extra_instructions: str,
    requires_math: bool = False,
) -> list[Question]:
    """
    Generate AI questions based on a topic for a flow.
    """
    try:
        model = "o4-mini" if requires_math else "gpt-4.1"

        logger.info(
            f"Generating {n_questions} AI questions for flow {flow.id} with topic: {flow.input_topic}"
        )

        system_message = (
            SYSTEM_MESSAGE_QUESTION_GENERATION_THEME_MATH
            if requires_math
            else SYSTEM_MESSAGE_QUESTION_GENERATION_THEME
        )
        user_message = f"Crie {n_questions} questões sobre: {flow.input_topic}"

        if extra_instructions:
            user_message += f"\n\nInstruções adicionais: {extra_instructions}"

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

        response = (
            await openai_utils.get_completion_parsed(
                model=model,
                temperature=0.5,
                messages=messages,
                response_format=QuestionSet,
                reasoning_effort="high",
                timeout=60,
            )
            if requires_math
            else await openai_utils.get_completion_parsed(
                model=model,
                temperature=0.5,
                messages=messages,
                response_format=QuestionSet,
                timeout=60,
            )
        )

        questions_data = response.content

        questions = []
        for question_data in questions_data.questions:
            # Apply delatexify for math subjects
            question_text = question_data.text
            if requires_math:
                question_text = LatexNodes2Text().latex_to_text(question_text)

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

            choices = []
            correct_choice_letter = question_data.correct_choice  # "A", "B", "C", "D"
            correct_choice_index = ord(correct_choice_letter.upper()) - ord(
                "A"
            )  # Converte para 0, 1, 2, 3
            # Create list of choice data with correctness flags
            choice_data_list = []
            for choice_order, choice_text in enumerate(question_data.choices):
                # Apply delatexify for math subjects
                delatexified_choice_text = choice_text
                if requires_math:
                    delatexified_choice_text = LatexNodes2Text().latex_to_text(
                        choice_text
                    )

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

            max_num_questions = n_questions
            flow.max_num_questions = max_num_questions
            db_session.add(flow)
            await db_session.flush()

        logger.info(
            f"Successfully generated {len(questions)} AI questions for flow {flow.id}"
        )
        return questions

    except Exception as e:
        logger.error(f"Error generating AI questions for flow {flow.id}: {str(e)}")
        await db_session.rollback()
        raise


async def get_files_user_generated_questions(
    db_session: AsyncSession,
    flow: Flow,
    n_questions: int,
    prompt_type: PromptType,
    extra_instructions: str,
    requires_math: bool = False,
) -> list[Question]:
    """
    Generate AI questions based on uploaded files for a flow.
    """
    try:
        model = "o4-mini" if requires_math else "gpt-4.1"

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

        logger.info(
            f"generating max_num_questions: {max_num_questions} for flow {flow.id}"
        )

        # Create tasks for parallel processing of each block
        async def process_block(block, block_index):
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

            messages = [
                {
                    "role": "system",
                    "content": system_message,
                },
                {"role": "user", "content": user_message},
            ]

            try:
                response = (
                    await openai_utils.get_completion_parsed(
                        model=model,
                        temperature=0.5,
                        messages=messages,
                        response_format=QuestionSet,
                        timeout=30,
                        reasoning_effort="high",
                    )
                    if requires_math
                    else await openai_utils.get_completion_parsed(
                        model=model,
                        temperature=0.5,
                        messages=messages,
                        response_format=QuestionSet,
                        timeout=30,
                    )
                )

                questions_data = response.content
                block_questions = []

                for question_data in questions_data.questions:
                    # Apply delatexify for math subjects
                    question_text = question_data.text
                    if requires_math:
                        question_text = LatexNodes2Text().latex_to_text(question_text)

                    # Create question dict with all necessary data
                    question_dict = {
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
        tasks = [
            process_block(block, i) for i, block in enumerate(transcription_blocks)
        ]
        block_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results in order and create database objects
        all_questions = []
        for block_index, block_questions in enumerate(block_results):
            if isinstance(block_questions, BaseException):
                logger.error(f"Exception in block {block_index + 1}: {block_questions}")
                continue
            else:
                for question_dict in block_questions:
                    question_data = question_dict["question_data"]
                    question_text = question_dict["question_text"]

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

                    choices = []
                    correct_choice_letter = (
                        question_data.correct_choice
                    )  # "A", "B", "C", "D"
                    correct_choice_index = ord(correct_choice_letter.upper()) - ord(
                        "A"
                    )  # Converte para 0, 1, 2, 3

                    # Create list of choice data with correctness flags
                    choice_data_list = []
                    for choice_order, choice_text in enumerate(question_data.choices):
                        # Apply delatexify for math subjects
                        delatexified_choice_text = choice_text
                        if requires_math:
                            delatexified_choice_text = LatexNodes2Text().latex_to_text(
                                choice_text
                            )

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

                    all_questions.append(question)

        logger.info(
            f"Successfully generated {len(all_questions)} AI questions from files for flow {flow.id}"
        )
        return all_questions

    except Exception as e:
        logger.error(
            f"Error generating AI questions from files for flow {flow.id}: {str(e)}"
        )
        raise


async def get_topic_query_official_questions(
    db_session: AsyncSession,
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
    """
    try:
        logger.info(
            f"Getting {n_questions} official questions for flow {flow.id} based on topic"
        )

        # Create embedding for the topic
        embeddings = None
        if flow.input_topic:
            embedding = await openai_utils.compute_embedding(flow.input_topic)
            embeddings = [embedding]

        # Use the generalized function
        questions = await get_official_questions(
            db_session=db_session,
            n_questions=n_questions,
            question_area_name=question_area_name,
            exam_id=exam_id,
            exam_country_code=exam_country_code,
            exam_education_level_id=exam_education_level_id,
            source_year=source_year,
            question_type=question_type,
            embeddings=embeddings,
            ensure_privileged_mix=(
                exam_id is None
            ),  # Only ensure mix if no specific exam
        )

        max_num_questions = n_questions
        flow.max_num_questions = max_num_questions
        db_session.add(flow)
        await db_session.flush()

        logger.info(f"Found {len(questions)} official questions for flow {flow.id}")
        return questions

    except Exception as e:
        logger.error(f"Error getting official questions for flow {flow.id}: {str(e)}")
        raise


async def get_files_query_official_questions(
    db_session: AsyncSession,
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
    """
    try:
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

        logger.info(
            f"getting max_num_questions: {max_num_questions} for flow {flow.id}"
        )

        # Phase 1: Generate all embeddings in parallel (slow I/O operations)
        logger.info(
            f"Generating embeddings for {len(block_titles)} block titles in parallel"
        )

        async def compute_embedding_for_title(block_title, block_index):
            """Compute embedding for a single block title"""
            try:
                embedding = await openai_utils.compute_embedding(block_title)
                return embedding
            except Exception as e:
                logger.error(
                    f"Error computing embedding for block {block_index + 1} ('{block_title}'): {str(e)}"
                )
                return None

        # Execute all embedding computations in parallel
        embedding_tasks = [
            compute_embedding_for_title(block_title, i)
            for i, block_title in enumerate(block_titles)
        ]
        embeddings = await asyncio.gather(*embedding_tasks, return_exceptions=True)

        # Phase 2: Get questions sequentially (fast DB queries with proper deduplication)
        logger.info(f"Getting questions sequentially for proper deduplication")

        all_questions = []
        unique_question_ids = set()

        for i, (block_title, embedding) in enumerate(zip(block_titles, embeddings)):
            if isinstance(embedding, BaseException):
                logger.error(
                    f"Skipping block {i + 1} due to embedding error: {embedding}"
                )
                continue

            if embedding is None:
                logger.warning(
                    f"Skipping block {i + 1} due to failed embedding generation"
                )
                continue

            try:
                # Get questions using the generalized function with proper exclusion
                block_questions = await get_official_questions(
                    db_session=db_session,
                    n_questions=n_questions,
                    question_area_name=question_area_name,
                    exam_id=exam_id,
                    exam_country_code=exam_country_code,
                    exam_education_level_id=exam_education_level_id,
                    source_year=source_year,
                    question_type=question_type,
                    embeddings=[embedding],
                    exclude_question_ids=unique_question_ids,  # Properly exclude previous questions
                    ensure_privileged_mix=True,
                )

                # Add unique questions to our list
                added_count = 0
                for question in block_questions:
                    if question.id not in unique_question_ids:
                        all_questions.append(question)
                        unique_question_ids.add(question.id)
                        added_count += 1

                logger.info(
                    f"Block {i + 1} ('{block_title[:50]}...'): {added_count} new questions added (total: {len(all_questions)})"
                )

            except Exception as e:
                logger.error(
                    f"Error getting questions for block {i + 1} ('{block_title}'): {str(e)}"
                )
                continue

        logger.info(f"Found {len(all_questions)} official questions for flow {flow.id}")
        return all_questions

    except Exception as e:
        logger.error(f"Error getting official questions for flow {flow.id}: {str(e)}")
        raise


async def add_questions_to_flow(
    db_session: AsyncSession,
    flow_id: int,
    questions: list[Question],
    start_order: int = 0,
) -> None:
    """
    Add a list of questions to a flow as FlowQuestion elements.
    """
    try:
        logger.info(f"Adding {len(questions)} questions to flow {flow_id}")

        # Only start a new transaction if we're not already in one
        if not db_session.in_transaction():
            await db_session.begin()

        flow_questions = []
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

        logger.info(
            f"Successfully added {len(flow_questions)} questions to flow {flow_id}"
        )

    except Exception as e:
        logger.error(f"Error adding questions to flow {flow_id}: {str(e)}")
        raise


async def _generate_block_title(block_text: str) -> str:
    """Generate a concise title/query for a transcription block."""
    try:
        response = await openai_utils.get_completion(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE_BLOCK_TITLE},
                {"role": "user", "content": block_text},
            ],
            json_mode=False,
            timeout=15,
            temperature=0.5,
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
            model="gpt-4.1-nano",
            temperature=0.5,
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
        )

        title = result.content.strip()
        # Ensure title is not too long
        if len(title) > 60:
            title = title[:57] + "..."

        return title if title else "Material de Estudo"

    except Exception as e:
        logger.error(f"Error generating title from transcriptions: {e}")
        return "Material de Estudo"


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
