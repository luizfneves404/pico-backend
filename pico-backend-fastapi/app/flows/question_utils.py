"""
FastAPI-adapted question utilities for categorization, answer generation, and quantitative analysis.
This module provides modern FastAPI implementations of key question processing functions.
All functions are implemented as ARQ tasks for use in admin actions.
"""

import functools
import logging
import operator
from collections import Counter
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Text, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.flows.prompts as flow_prompts
from app.database import get_db_session_for_worker
from app.files.models import File
from app.flows.db_types import (
    ImageBlockDB,
    RichText,
    TextBlock,
    validate_content_block_list,
)
from app.flows.models import (
    ENEM_AREAS,
    Exam,
    Flow,
    FlowQuestion,
    OfficialQuestionSource,
    Question,
    QuestionSourceType,
)
from app.shared import openai_utils

logger = logging.getLogger(__name__)

QUESTION_EMBEDDING_BATCH_SIZE = 1000


class MinorTagsCategorization(BaseModel):
    """Response model for minor tags categorization."""

    minor_tags: list[str]


class MajorTagCategorization(BaseModel):
    """Response model for major tag (subject) categorization."""

    major_tag: str


class QuantitativeAnalysis(BaseModel):
    """Response model for quantitative analysis."""

    requires_paper: bool


class AnswerGeneration(BaseModel):
    """Response model for answer generation."""

    answer_text: str


async def categorize_minor_tags(
    db_session: AsyncSession, question_id: int
) -> MinorTagsCategorization:
    """
    Generate minor tags for a question using TAGS approach with gpt-5-mini.
    Focuses only on central topics/themes of the question.

    Args:
        db_session: Database session
        question_id: ID of the question to categorize

    Returns:
        MinorTagsCategorization: Categorization result with minor tags only
    """
    # Get question with choices
    question = await db_session.scalar(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.choices))
    )

    if not question:
        raise ValueError(f"Question {question_id} not found")

    # Get complete question text with choices
    question_text_with_choices = question.question_text_with_choices_text

    if not question_text_with_choices:
        logger.info(f"Skipping question without text or choices: {question_id}")
        return MinorTagsCategorization(minor_tags=[])

    # Get question image URLs
    image_urls = await get_question_image_urls(db_session, question)

    # Generate minor tags using the full categorization system
    minor_tags = await _generate_minor_tags(question_text_with_choices, image_urls)

    result = MinorTagsCategorization(minor_tags=minor_tags)

    logger.info(f"Categorized question {question_id}: {result}")
    return result


async def generate_answer(
    db_session: AsyncSession,
    question_id: int,
) -> AnswerGeneration:
    """
    Generate answer explanation using gpt-5 model.

    Args:
        db_session: Database session
        question_id: ID of the question to generate answer for

    Returns:
        AnswerGeneration: Generated answer and explanation
    """
    # Get question with choices
    question = await db_session.scalar(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.choices))
    )

    if not question:
        raise ValueError(f"Question {question_id} not found")

    # Get question text and choices
    question_text = question.question_text_with_choices_text

    if not question_text:
        raise ValueError(f"Question {question_id} has no text or choices")

    # Find the correct choice letter for reference
    correct_choice_letter = None
    for i, choice in enumerate(question.choices):
        if choice.is_correct:
            correct_choice_letter = chr(65 + i)  # A, B, C, D, E
            break

    if not correct_choice_letter:
        raise ValueError(f"Question {question_id} has no correct choice marked")

    # Get question image URLs
    image_urls = await get_question_image_urls(db_session, question)

    response = await flow_prompts.GenerateAnswer().text(
        question_text_with_choices=question_text,
        correct_choice_letter=correct_choice_letter,
        image_urls=image_urls,
    )

    # Use the complete response as the answer (simplified approach)
    content = response.strip()

    return AnswerGeneration(
        answer_text=content,
    )


async def is_quantitative(
    question_text_with_choices: str,
    image_urls: list[str] | None = None,
) -> QuantitativeAnalysis:
    """
    Analyze if a question requires paper to be solved using gpt-5.

    Args:
        question_text_with_choices: Complete question text with choices
        image_urls: List of image URLs for the question

    Returns:
        QuantitativeAnalysis: Analysis of whether question requires paper
    """
    if image_urls is None:
        image_urls = []

    response = await flow_prompts.IsQuantitative().text(
        question_text_with_choices=question_text_with_choices,
        image_urls=image_urls,
    )

    # Parse the simple true/false response
    response_text = response.strip().lower()
    requires_paper = response_text == "true"

    result = QuantitativeAnalysis(requires_paper=requires_paper)
    logger.info(
        f"Quantitative analysis completed: requires_paper={result.requires_paper}"
    )
    return result


# Helper functions


async def get_question_image_urls(
    db_session: AsyncSession, question: Question
) -> list[str]:
    """
    Extract image URLs from question content blocks.

    Args:
        db_session: Database session
        question: Question instance

    Returns:
        list[str]: List of image URLs
    """
    image_urls: list[str] = []

    # Extract image IDs from content blocks
    image_ids: list[int] = [
        block.image_id
        for block in question.content_blocks
        if isinstance(block, ImageBlockDB)
    ]

    # Get File objects and URLs
    if image_ids:
        files = await db_session.scalars(select(File).where(File.id.in_(image_ids)))
        for file in files:
            try:
                url = await file.get_url()
                image_urls.append(url)
            except Exception as e:
                logger.warning(f"Error getting URL for file {file.id}: {e}")
                continue

    return image_urls


async def categorize_major_tag(
    db_session: AsyncSession, question_id: int
) -> MajorTagCategorization:
    """
    Generate major tag (subject) for a question using gpt-5-mini.

    Args:
        db_session: Database session
        question_id: ID of the question to categorize

    Returns:
        MajorTagCategorization: Major tag (subject) categorization result
    """
    # Get question with choices
    question = await db_session.scalar(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.choices))
    )

    if not question:
        raise ValueError(f"Question {question_id} not found")

    # Get complete question text with choices
    question_text_with_choices = question.question_text_with_choices_text

    if not question_text_with_choices:
        logger.info(f"Skipping question without text or choices: {question_id}")
        return MajorTagCategorization(major_tag="Questão Discursiva")

    # Get question image URLs
    image_urls = await get_question_image_urls(db_session, question)

    # Classify the subject using ENEM areas approach
    major_tag = await _classify_question_subject(question_text_with_choices, image_urls)

    result = MajorTagCategorization(major_tag=major_tag)

    logger.info(f"Classified major tag for question {question_id}: {major_tag}")
    return result


async def _classify_question_subject(
    question_text_with_choices: str, image_urls: list[str] | None = None
) -> str:
    """
    Classify question subject to determine major tag.
    Uses the original subject classification approach from utils.py.
    """
    image_urls = image_urls or []

    try:
        # First pass: try area by area
        for subjects in ENEM_AREAS.values():
            response = await flow_prompts.ClassifyQuestionSubject().text(
                subjects=subjects,
                question_text_with_choices=question_text_with_choices,
                image_urls=image_urls,
            )

            response_text = response.strip()
            if response_text in subjects:
                return response_text

        # Fallback: try all subjects at once
        all_subjects = functools.reduce(operator.iadd, ENEM_AREAS.values(), [])

        response = await flow_prompts.ClassifyQuestionSubject().text(
            subjects=all_subjects,
            question_text_with_choices=question_text_with_choices,
            image_urls=image_urls,
        )

        response_text = response.strip()
        if response_text in all_subjects:
            return response_text

    except Exception:
        logger.exception("Error classifying question subject")
        return "Conhecimentos Gerais"
    else:
        return "Conhecimentos Gerais"


async def _generate_minor_tags(
    question_text_with_choices: str,
    image_urls: list[str] | None = None,
) -> list[str]:
    """Generate minor tags for detailed categorization."""
    if image_urls is None:
        image_urls = []

    try:
        response = await flow_prompts.GenerateMinorTagsFromQuestion().text(
            question_text_with_choices=question_text_with_choices,
            image_urls=image_urls,
        )

        # Parse the response to extract tags
        content = response.strip()

        # Simple parsing - look for comma-separated tags
        if "," in content:
            tags = [tag.strip() for tag in content.split(",")]
            return tags[:5]  # Max 5 minor tags
        # Single tag response

    except Exception:
        logger.exception("Error generating minor tags")
        return []
    else:
        return [content] if content else []


# =============================================================================
# ARQ TASKS for Admin Actions
# =============================================================================


async def task_categorize_minor_tags(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
) -> None:
    """
    Task to categorize questions and save minor tags in Question.minor_tags field.
    When question_ids is None (admin case), only process active questions.
    When question_ids is provided (AI questions case), process regardless of is_active status.
    """
    async with get_db_session_for_worker(ctx) as session:
        # Get questions to categorize
        if question_ids is None:
            # Admin case: only process active questions
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.is_active.is_(True))
            )
        else:
            # Specific questions case (AI): process regardless of is_active status
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.id.in_(question_ids))
            )

        result = await session.execute(stmt)
        questions: list[Question] = list(result.scalars())

        logger.info(f"Starting categorization for {len(questions)} questions")

        # Process each question
        for question in questions:
            try:
                # Generate minor tags
                categorization = await categorize_minor_tags(session, question.id)

                # Save minor tags to question
                question.minor_tags = categorization.minor_tags

                logger.info(
                    f"Categorized question {question.id} with tags: {categorization.minor_tags}"
                )

            except Exception:
                logger.exception(f"Error categorizing question {question.id}")
                continue

        logger.info(
            f"Completed minor tags categorization for {len(questions)} questions"
        )


async def task_categorize_major_tags(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
) -> None:
    """
    Task to classify question subjects and save major tags in Question.major_tags field.
    When question_ids is None (admin case), only process active questions.
    When question_ids is provided (AI questions case), process regardless of is_active status.
    """
    async with get_db_session_for_worker(ctx) as session:
        # Get questions to categorize
        if question_ids is None:
            # Admin case: only process active questions
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.is_active.is_(True))
            )
        else:
            # Specific questions case (AI): process regardless of is_active status
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.id.in_(question_ids))
            )

        result = await session.execute(stmt)
        questions: list[Question] = list(result.scalars())

        logger.info(f"Starting major tag classification for {len(questions)} questions")

        # Process each question
        for question in questions:
            try:
                # Generate major tag (subject)
                categorization = await categorize_major_tag(session, question.id)

                # Save major tag to question (as single item list)
                question.major_tags = [categorization.major_tag]

                logger.info(
                    f"Classified question {question.id} with major tag: {categorization.major_tag}"
                )

            except Exception:
                logger.exception(f"Error classifying question {question.id}")
                continue

        logger.info(
            f"Completed major tag classification for {len(questions)} questions"
        )


async def task_generate_question_answers(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
) -> None:
    """
    Task to generate answers for questions and save in Question.answer_content_blocks field.
    When question_ids is None (admin case), only process active questions.
    When question_ids is provided (AI questions case), process regardless of is_active status.
    """
    async with get_db_session_for_worker(ctx) as session:
        # Get questions to generate answers for
        if question_ids is None:
            # Admin case: only process active questions
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.is_active.is_(True))
            )
        else:
            # Specific questions case (AI): process regardless of is_active status
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.id.in_(question_ids))
            )

        result = await session.execute(stmt)
        questions: list[Question] = list(result.scalars())

        logger.info(f"Starting answer generation for {len(questions)} questions")

        # Process each question
        for question in questions:
            try:
                # Skip if answer already exists
                if question.answer_content_blocks:
                    logger.info(f"Answer already exists for question {question.id}")
                    continue

                # Generate answer
                answer_generation = await generate_answer(session, question.id)

                # Create answer content blocks
                answer_text_block = TextBlock(
                    block_type="text",
                    style="paragraph",
                    content=[
                        RichText(
                            text=answer_generation.answer_text,
                            bold=False,
                            italic=False,
                            underline=False,
                            strikethrough=False,
                            link=None,
                        )
                    ],
                )

                question.answer_content_blocks = validate_content_block_list(
                    [answer_text_block]
                )

                logger.info(f"Generated answer for question {question.id}")

            except Exception:
                logger.exception(f"Error generating answer for question {question.id}")
                continue

        logger.info(f"Completed answer generation for {len(questions)} questions")


async def task_analyze_question_quantitativeness(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
) -> None:
    """
    Task to analyze if questions require paper and save in Question.is_quantitative field.
    When question_ids is None (admin case), only process active questions.
    When question_ids is provided (AI questions case), process regardless of is_active status.
    """
    async with get_db_session_for_worker(ctx) as session:
        # Get questions to analyze
        if question_ids is None:
            # Admin case: only process active questions
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.is_active.is_(True))
            )
        else:
            # Specific questions case (AI): process regardless of is_active status
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.id.in_(question_ids))
            )

        result = await session.execute(stmt)
        questions: list[Question] = list(result.scalars())

        logger.info(f"Starting quantitative analysis for {len(questions)} questions")

        # Process each question
        for question in questions:
            try:
                # Get complete question text with choices
                question_text_with_choices = question.question_text_with_choices_text

                if not question_text_with_choices:
                    logger.info(
                        f"Skipping question without text or choices: {question.id}"
                    )
                    question.is_quantitative = False
                    continue

                # Get question image URLs
                image_urls = await get_question_image_urls(session, question)

                # Analyze quantitativeness
                analysis = await is_quantitative(question_text_with_choices, image_urls)

                # Save to question
                question.is_quantitative = analysis.requires_paper

                logger.info(
                    f"Analyzed question {question.id}: requires_paper={analysis.requires_paper}"
                )

            except Exception:
                logger.exception(f"Error analyzing question {question.id}")
                continue

        logger.info(f"Completed quantitative analysis for {len(questions)} questions")


def _build_question_embedding_text(question: Question) -> str:
    """
    Builds the single embedding text for a question.

    Args:
        question: Question ORM object with relationships loaded.

    Returns:
        Combined string containing question text, choices, optional source and tags info.
    """
    parts: list[str] = []
    if question.question_text:
        parts.append(question.question_text)
    if question.choices_text:
        parts.append(question.choices_text)
    if question.source_info:
        parts.append(question.source_info)
    if question.tags_info:
        parts.append(question.tags_info)
    return "\n\n".join(parts)


async def _fetch_matching_question_ids(
    ctx: dict[str, Any],
    condition: Any,
) -> list[int]:
    """
    Fetches all question IDs that match the given condition.

    Args:
        ctx: ARQ worker context.
        condition: SQLAlchemy boolean expression to filter questions.

    Returns:
        List of matching question IDs.
    """
    async with get_db_session_for_worker(ctx) as session:
        result = await session.execute(select(Question.id).where(condition))
        return list(result.scalars())


async def _process_question_embedding_batches(
    ctx: dict[str, Any],
    all_ids: list[int],
) -> int:
    """
    Loads questions in batches, computes embeddings and stores them.

    Args:
        ctx: ARQ worker context.
        all_ids: Question IDs to process.

    Returns:
        Total number of questions processed.
    """
    processed_count = 0
    num_questions = len(all_ids)

    for batch_start in range(0, num_questions, QUESTION_EMBEDDING_BATCH_SIZE):
        batch_ids = all_ids[batch_start : batch_start + QUESTION_EMBEDDING_BATCH_SIZE]

        async with get_db_session_for_worker(ctx) as session:
            stmt = (
                select(Question)
                .options(
                    selectinload(Question.choices),
                    selectinload(Question.official_source)
                    .selectinload(OfficialQuestionSource.exam)
                    .selectinload(Exam.country),
                )
                .where(Question.id.in_(batch_ids))
            )
            result = await session.execute(stmt)
            questions: list[Question] = list(result.scalars())

            logger.info(
                f"Processing batch {batch_start // QUESTION_EMBEDDING_BATCH_SIZE + 1}. "
                f"We are at question {batch_start + 1} of {num_questions} questions."
            )

            texts_for_embedding = [_build_question_embedding_text(q) for q in questions]
            embeddings = await openai_utils.compute_embedding(texts_for_embedding)

            for question, embedding in zip(questions, embeddings, strict=False):
                question.embedding = embedding

        processed_count += len(questions)

    return processed_count


async def task_compute_question_embeddings(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
) -> None:
    """
    Asynchronously computes and stores embeddings for questions in batches.

    When question_ids is None, only process active official questions without an embedding.
    When question_ids is provided, process those IDs regardless of is_active.

    Args:
        ctx: ARQ worker context
        question_ids: List of question IDs to process, None means filtered set
    """
    if question_ids is None:
        condition = (
            Question.is_active.is_(True)
            & (Question.source_type == QuestionSourceType.OFFICIAL)
            & Question.embedding.is_(None)
        )
    else:
        condition = Question.id.in_(question_ids)

    all_ids = await _fetch_matching_question_ids(ctx, condition)
    num_questions = len(all_ids)
    logger.info(f"Computing embeddings for {num_questions} questions")

    processed_count = await _process_question_embedding_batches(
        ctx=ctx,
        all_ids=all_ids,
    )
    logger.info(f"Computed embeddings for {processed_count} questions")


async def task_recompute_question_embeddings(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
) -> None:
    """
    Recompute embeddings for questions, overriding existing ones.

    When question_ids is None, process all active official questions.
    When question_ids is provided, process those IDs regardless of is_active.

    Args:
        ctx: ARQ worker context
        question_ids: List of question IDs to process, None means all active official questions
    """
    if question_ids is None:
        condition = Question.is_active.is_(True) & (
            Question.source_type == QuestionSourceType.OFFICIAL
        )
    else:
        condition = Question.id.in_(question_ids)

    all_ids = await _fetch_matching_question_ids(ctx, condition)
    num_questions = len(all_ids)
    logger.info(
        f"Recomputing embeddings for {num_questions} questions (ignoring existing embeddings)"
    )

    processed_count = await _process_question_embedding_batches(
        ctx=ctx,
        all_ids=all_ids,
    )
    logger.info(f"Recomputed embeddings for {processed_count} questions")


async def task_fix_question_newlines(
    ctx: dict[str, Any], question_ids: list[int] | None
) -> None:
    async with get_db_session_for_worker(ctx) as session:
        stmt = update(Question).values(
            content_blocks=func.replace(
                Question.content_blocks.cast(Text), "\\\\n", "\\n"
            ).cast(JSONB),
            answer_content_blocks=func.replace(
                Question.answer_content_blocks.cast(Text), "\\\\n", "\\n"
            ).cast(JSONB),
        )

        if question_ids is None:
            stmt = stmt.where(Question.is_active.is_(True))
        else:
            stmt = stmt.where(Question.id.in_(question_ids))

        await session.execute(stmt)


async def task_categorize_questions(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
) -> None:
    """
    Asynchronously categorizes questions using TAGS approach.
    When question_ids is None (admin case), only process active questions.
    When question_ids is provided (AI questions case), process regardless of is_active status.

    Args:
        ctx: ARQ worker context
        question_ids: List of question IDs to process, None means all questions
    """
    async with get_db_session_for_worker(ctx) as session:
        if question_ids is None:
            # Admin case: only process active questions
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.is_active.is_(True))
            )
        else:
            # Specific questions case (AI): process regardless of is_active status
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.id.in_(question_ids))
            )

        result = await session.execute(stmt)
        questions: list[Question] = list(result.scalars())

        if not questions:
            logger.info("No questions found for categorization")
            return

        categorized_count = 0

        for question in questions:
            try:
                choices = [choice.text for choice in question.choices]

                if not choices:
                    logger.info(f"Skipping open-ended question {question.id}")
                    continue

                # Get complete question text with choices
                question_text_with_choices = question.question_text_with_choices_text

                if not question_text_with_choices:
                    logger.warning(f"Question {question.id} has no text or choices")
                    continue

                # Get question image URLs
                image_urls = await get_question_image_urls(session, question)

                # Classify subject/area for major tag
                major_tag = await _classify_question_subject(
                    question_text_with_choices, image_urls
                )

                # Generate minor tags
                minor_tags = await _generate_minor_tags(
                    question_text_with_choices, image_urls
                )

                # Update question with tags
                if major_tag:
                    question.major_tags = [major_tag]
                if minor_tags:
                    question.minor_tags = minor_tags

                categorized_count += 1
                logger.debug(
                    f"Categorized question {question.id}: major={major_tag}, minor={minor_tags}"
                )

            except Exception:
                logger.exception(f"Error categorizing question {question.id}")
                continue

        logger.info(f"Categorized {categorized_count} questions")


async def task_consolidate_flow_tags(
    ctx: dict[str, Any],
    flow_id: int,
) -> None:
    """
    Task to consolidate question tags into flow tags.
    Collects the most frequent minor tags and the most frequent major tag from questions
    in the flow and applies them to the flow.
    """
    async with get_db_session_for_worker(ctx) as session:
        # Get flow
        flow = await session.scalar(select(Flow).where(Flow.id == flow_id))
        if not flow:
            logger.error(f"Flow {flow_id} not found")
            return

        stmt = (
            select(Question)
            .join(FlowQuestion, Question.id == FlowQuestion.question_id)
            .where(
                FlowQuestion.flow_id == flow_id,
                Question.source_type == QuestionSourceType.AI_GENERATED,
            )
        )

        result = await session.execute(stmt)
        questions = list(result.scalars())

        if not questions:
            logger.info(f"No AI-generated questions found for flow {flow_id}")
            return

        # Collect all minor tags from questions
        all_minor_tags: list[str] = []
        all_major_tags: list[str] = []

        for question in questions:
            if question.minor_tags:
                clean_minor_tags = [
                    tag.strip().lower() for tag in question.minor_tags if tag.strip()
                ]
                all_minor_tags.extend(clean_minor_tags)

            if question.major_tags:
                clean_major_tags = [
                    tag.strip() for tag in question.major_tags if tag.strip()
                ]
                all_major_tags.extend(clean_major_tags)

        # Find top minor tags (TOP_TAGS_COUNT from question_service.py)
        TOP_TAGS_COUNT = 10
        if all_minor_tags:
            minor_tag_counter = Counter(all_minor_tags)
            top_minor_tags = [
                tag for tag, _ in minor_tag_counter.most_common(TOP_TAGS_COUNT)
            ]
            flow.minor_tags = top_minor_tags
            logger.info(
                f"Applied top {TOP_TAGS_COUNT} minor tags to flow {flow_id}: {top_minor_tags}"
            )

        # Find most frequent major tag (only 1)
        if all_major_tags:
            major_tag_counter = Counter(all_major_tags)
            top_major_tag = major_tag_counter.most_common(1)[0][0]
            flow.major_tags = [top_major_tag]
            logger.info(f"Applied major tag to flow {flow_id}: {top_major_tag}")

        # Save changes
        session.add(flow)

        logger.info(
            f"Successfully consolidated tags for flow {flow_id} from {len(questions)} questions"
        )


async def task_generate_and_consolidate_tags(
    ctx: dict[str, Any],
    question_ids: list[int],
    flow_id: int,
) -> None:
    """
    Orchestrator task that ensures proper sequencing of tag generation and consolidation.

    1. First generates minor tags for all questions
    2. Then generates major tags for all questions
    3. Finally consolidates the tags into the flow

    This ensures the consolidation only happens after all individual tags are generated.
    """
    logger.info(
        f"Starting tag generation orchestrator for {len(question_ids)} questions in flow {flow_id}"
    )

    # Step 1: Generate minor tags (wait for completion)
    logger.info(f"Step 1/3: Generating minor tags for {len(question_ids)} questions")
    await task_categorize_minor_tags(ctx, question_ids)

    # Step 2: Generate major tags (wait for completion)
    logger.info(f"Step 2/3: Generating major tags for {len(question_ids)} questions")
    await task_categorize_major_tags(ctx, question_ids)

    # Step 3: Consolidate tags into flow (only after steps 1 & 2 complete)
    logger.info(f"Step 3/3: Consolidating tags for flow {flow_id}")
    await task_consolidate_flow_tags(ctx, flow_id)

    logger.info(
        f"Successfully completed tag generation orchestrator for flow {flow_id}"
    )
