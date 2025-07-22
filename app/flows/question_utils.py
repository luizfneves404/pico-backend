"""
FastAPI-adapted question utilities for categorization, answer generation, and quantitative analysis.
This module provides modern FastAPI implementations of key question processing functions.
All functions are implemented as ARQ tasks for use in admin actions.
"""

import logging
from typing import Any

from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.database import get_db_session_for_worker
from app.flows.models import Question, ENEM_AREAS
from app.files.models import File
from app.flows.db_types import (
    ContentBlock,
    RichText,
    TextBlock,
    validate_content_block_list,
)
from app.shared import openai_utils

logger = logging.getLogger(__name__)


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


# System messages adapted from original utils.py
SYSTEM_MESSAGE_MINOR_TAGS = """
Você é um especialista em gerar tags que indiquem o conteúdo abordado para questões de vestibular.
Você receberá o enunciado e as alternativas de uma questão específica e deverá gerar tags que identifiquem o(s) tema(s) abordado(s) nessa questão.

INSTRUÇÕES:
- Analise cuidadosamente o enunciado da questão e suas alternativas
- Identifique de 1 a 5 tags que melhor representem os TÓPICOS CENTRAIS específicos abordados na questão
- As tags devem ser específicas e refletir os conceitos/tópicos da questão apresentada
- Caso opte por mais de uma tag, não seja redundante, ou seja, não repita tags ou use tags que sejam muito parecidas
- O modelo tem liberdade para criar tags apropriadas que capturem o conteúdo da questão

FORMATO DE RESPOSTA OBRIGATÓRIO:
- Retorne APENAS as tags separadas por vírgula (ex: "Tag1, Tag2, Tag3")
- De 1 a 5 tags por questão
- Sem pontuação adicional, aspas, explicações ou texto extra
"""

SYSTEM_MESSAGE_MAJOR_TAG = """
Você é um professor especializado em vestibulares e deve dizer qual a matéria da questão que é enviadas a você.
A mensagem enviada terá:
    - Um enunciado
    - O texto extraído da questão (opcional, pode estar em branco)
    - Quatro ou cinco alternativas, com indicações se são corretas ou incorretas
Com base nessas informações, você deve definir em que matéria está a questão, usando a lista de matérias abaixo. Tente responder considerando que tipos de conhecimento ou competências são avaliados na questão e os temas com que se relacionam. Escolha apenas uma matéria.
Responda apenas o nome da matéria escolhida, sem nenhum detalhamento ou justificativa.
Escreva SOMENTE matérias que estejam mencionadas a seguir, e nenhuma outra, sem utilizar aspas. As matérias disponíveis são:
{subjects}
"""

SYSTEM_MESSAGE_IS_QUANTITATIVE = """
Você é um assistente que classifica questões de vestibular quanto à necessidade de usar papel para resolução.

Analise se a questão PRECISA DE PAPEL PARA SER RESOLVIDA considerando:

PRECISA DE PAPEL:
- Cálculos matemáticos complexos que não podem ser feitos mentalmente  
- Desenhos, gráficos ou esquemas necessários para a resolução
- Múltiplas etapas de cálculo que requerem anotações
- Manipulação algébrica ou geométrica extensa
- Problemas que envolvem construções ou diagramas

NÃO PRECISA DE PAPEL:
- Questões puramente conceituais ou teóricas
- Cálculos mentais simples
- Questões de interpretação de texto
- Análise qualitativa sem cálculos

Responda APENAS "true" se precisa de papel ou "false" caso contrário.
Não inclua explicações ou comentários adicionais.
"""

SYSTEM_MESSAGE_GENERATE_ANSWER = """Você é um professor especializado na correção de vestibulares e deve escrever resoluções comentadas das questões que são enviadas para você.
As mensagens enviadas terão:
    - Um enunciado
    - (Opcional) uma descrição da imagem que complementa o enunciado
    - Quatro ou cinco alternativas, com indicações se são corretas ou incorretas
Com base nessas informações, você deve elaborar uma explicação concisa de por que a alternativa correta está correta e por que as demais estão erradas. Comente cada uma das alternativas incorretas e aponte o erro nelas. Por favor, seja minucioso nas suas análises e procure explicar detalhes específicos de cada alternativa quando necessário, sendo direto e conciso."""


async def categorize_minor_tags(
    db_session: AsyncSession, question_id: int, temperature: float = 0.2
) -> MinorTagsCategorization:
    """
    Generate minor tags for a question using TAGS approach with gpt-4.1-mini.
    Focuses only on central topics/themes of the question.

    Args:
        db_session: Database session
        question_id: ID of the question to categorize
        temperature: Temperature for AI model

    Returns:
        MinorTagsCategorization: Categorization result with minor tags only
    """
    try:
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
        minor_tags = await _generate_minor_tags(
            question_text_with_choices, temperature, image_urls
        )

        result = MinorTagsCategorization(minor_tags=minor_tags)

        logger.info(f"Categorized question {question_id}: {result}")
        return result

    except Exception as e:
        logger.error(f"Error categorizing question {question_id}: {str(e)}")
        raise


async def generate_answer(
    db_session: AsyncSession,
    question_id: int,
) -> AnswerGeneration:
    """
    Generate answer explanation using o3 model.

    Args:
        db_session: Database session
        question_id: ID of the question to generate answer for

    Returns:
        AnswerGeneration: Generated answer and explanation
    """
    try:
        # Get question with choices
        question = await db_session.scalar(
            select(Question)
            .where(Question.id == question_id)
            .options(selectinload(Question.choices))
        )

        if not question:
            raise ValueError(f"Question {question_id} not found")

        # Check if answer already exists
        if question.answer_content_blocks:
            logger.info(f"Answer already exists for question {question_id}")
            # Extract existing answer text
            existing_answer = ""
            for block in question.answer_content_blocks:
                if hasattr(block, "block_type") and block.block_type == "text":
                    # Handle TextBlock object
                    if hasattr(block, "content") and block.content:
                        for rich_text in block.content:
                            if hasattr(rich_text, "text"):
                                existing_answer += rich_text.text
                elif isinstance(block, dict) and block.get("type") == "text":
                    # Handle dict format
                    existing_answer += block.get("text", "")

            return AnswerGeneration(
                answer_text=existing_answer,
            )

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

        # Simple message - let the model use its full reasoning
        user_message = f"""
{question_text}

Alternativa correta: {correct_choice_letter}
"""

        # Build messages with images if available
        if image_urls:
            user_content = [{"type": "text", "text": user_message}]
            for image_url in image_urls:
                user_content.append(
                    {  # type: ignore
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "high"},
                    }
                )

            messages: list[ChatCompletionMessageParam] = [
                {"role": "system", "content": SYSTEM_MESSAGE_GENERATE_ANSWER},
                {"role": "user", "content": user_content},  # type: ignore
            ]
        else:
            messages: list[ChatCompletionMessageParam] = [
                {"role": "system", "content": SYSTEM_MESSAGE_GENERATE_ANSWER},
                {"role": "user", "content": user_message},
            ]

        # Use o3 model with reasoning effort for better quality
        response = await openai_utils.get_completion(
            model="o3",
            temperature=None,  # Temperature is ignored for reasoning models
            messages=messages,
            timeout=90,
            reasoning_effort="high",
        )

        # Use the complete response as the answer (simplified approach)
        content = response.content.strip()

        result = AnswerGeneration(
            answer_text=content,
        )

        logger.info(
            f"Generated answer for question {question_id} (using reasoning_effort=high)"
        )
        return result

    except Exception as e:
        logger.error(f"Error generating answer for question {question_id}: {str(e)}")
        raise


async def is_quantitative(
    question_text_with_choices: str,
    image_urls: list[str] | None = None,
) -> QuantitativeAnalysis:
    """
    Analyze if a question requires paper to be solved using o4-mini.

    Args:
        question_text_with_choices: Complete question text with choices
        image_urls: List of image URLs for the question

    Returns:
        QuantitativeAnalysis: Analysis of whether question requires paper
    """
    if image_urls is None:
        image_urls = []

    try:
        # Build messages with images if available
        if image_urls:
            user_content = [{"type": "text", "text": question_text_with_choices}]
            for image_url in image_urls:
                user_content.append(
                    {  # type: ignore
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "high"},
                    }
                )

            messages: list[ChatCompletionMessageParam] = [
                {"role": "system", "content": SYSTEM_MESSAGE_IS_QUANTITATIVE},
                {"role": "user", "content": user_content},  # type: ignore
            ]
        else:
            messages: list[ChatCompletionMessageParam] = [
                {"role": "system", "content": SYSTEM_MESSAGE_IS_QUANTITATIVE},
                {"role": "user", "content": question_text_with_choices},
            ]

        # Use o4-mini with medium reasoning effort
        response = await openai_utils.get_completion(
            model="o4-mini",
            temperature=None,
            messages=messages,
            timeout=30,
            reasoning_effort="medium",
        )

        # Parse the simple true/false response
        response_text = response.content.strip().lower()
        requires_paper = response_text == "true"

        result = QuantitativeAnalysis(requires_paper=requires_paper)
        logger.info(
            f"Quantitative analysis completed: requires_paper={result.requires_paper}"
        )
        return result

    except Exception as e:
        logger.error(f"Error in quantitative analysis: {str(e)}")
        raise


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
    image_ids: list[int] = []
    for block in question.content_blocks:
        if hasattr(block, "block_type") and block.block_type == "image":
            # Handle ImageBlock object
            if hasattr(block, "image_id"):
                image_ids.append(block.image_id)
        elif isinstance(block, dict) and block.get("block_type") == "image":
            # Handle dict format
            image_id = block.get("image_id")
            if image_id:
                image_ids.append(image_id)

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
    db_session: AsyncSession, question_id: int, temperature: float = 0.1
) -> MajorTagCategorization:
    """
    Generate major tag (subject) for a question using gpt-4.1-mini.

    Args:
        db_session: Database session
        question_id: ID of the question to categorize
        temperature: Temperature for AI model

    Returns:
        MajorTagCategorization: Major tag (subject) categorization result
    """
    try:
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
        major_tag = await _classify_question_subject(
            question_text_with_choices, image_urls
        )

        result = MajorTagCategorization(major_tag=major_tag)

        logger.info(f"Classified major tag for question {question_id}: {major_tag}")
        return result

    except Exception as e:
        logger.error(
            f"Error classifying major tag for question {question_id}: {str(e)}"
        )
        raise


async def _classify_question_subject(
    question_text_with_choices: str, image_urls: list[str] | None = None
) -> str:
    """
    Classify question subject to determine major tag.
    Uses the original subject classification approach from utils.py.
    """
    if image_urls is None:
        image_urls = []

    try:
        # First, determine which area this question belongs to
        best_area = None
        best_subject = None
        best_confidence = 0.0

        for area, subjects in ENEM_AREAS.items():
            system_message = SYSTEM_MESSAGE_MAJOR_TAG.format(
                subjects="\n".join(subjects)
            )

            user_message = f"""
Texto extraído: 

{question_text_with_choices}
"""

            # Build messages with images if available
            if image_urls:
                user_content = [{"type": "text", "text": user_message}]
                for image_url in image_urls:
                    user_content.append(
                        {  # type: ignore
                            "type": "image_url",
                            "image_url": {"url": image_url, "detail": "low"},
                        }
                    )

                messages = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_content},  # type: ignore
                ]
            else:
                messages = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ]

            response = await openai_utils.get_completion(
                model="gpt-4.1-mini",
                temperature=0.1,
                messages=messages,  # type: ignore
                timeout=20,
            )

            response_text = response.content.strip()

            # Check if the response is a valid subject from this area
            if response_text in subjects:
                # Use this subject as major tag
                return response_text

        # Fallback: try all subjects at once
        all_subjects = sum(ENEM_AREAS.values(), [])
        system_message = SYSTEM_MESSAGE_MAJOR_TAG.format(
            subjects="\n".join(all_subjects)
        )

        # Build fallback messages with images if available
        if image_urls:
            user_content = [{"type": "text", "text": user_message}]
            for image_url in image_urls:
                user_content.append(
                    {  # type: ignore
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "low"},
                    }
                )

            fallback_messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_content},  # type: ignore
            ]
        else:
            fallback_messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ]

        response = await openai_utils.get_completion(
            model="gpt-4.1-mini",
            temperature=0.1,
            messages=fallback_messages,  # type: ignore
            timeout=20,
        )

        response_text = response.content.strip()
        if response_text in all_subjects:
            return response_text

        # Final fallback
        return "Conhecimentos Gerais"

    except Exception as e:
        logger.error(f"Error classifying question subject: {str(e)}")
        return "Conhecimentos Gerais"


async def _generate_minor_tags(
    question_text_with_choices: str,
    temperature: float,
    image_urls: list[str] | None = None,
) -> list[str]:
    """Generate minor tags for detailed categorization."""
    if image_urls is None:
        image_urls = []

    try:
        system_message = SYSTEM_MESSAGE_MINOR_TAGS

        user_message = f"""
Questão completa:
{question_text_with_choices}

Analise a questão e identifique as tags mais apropriadas.
"""

        # Build message content with images if available
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_message}
        ]

        if image_urls:
            user_content = [{"type": "text", "text": user_message}]
            for image_url in image_urls:
                user_content.append(
                    {  # type: ignore
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "low"},
                    }
                )

            messages.append({"role": "user", "content": user_content})  # type: ignore
        else:
            messages.append({"role": "user", "content": user_message})

        response = await openai_utils.get_completion(
            model="gpt-4.1-mini",
            temperature=temperature,
            messages=messages,
            timeout=20,
        )

        # Parse the response to extract tags
        content = response.content.strip()

        # Simple parsing - look for comma-separated tags
        if "," in content:
            tags = [tag.strip() for tag in content.split(",")]
            return tags[:5]  # Max 5 minor tags
        else:
            # Single tag response
            return [content] if content else []

    except Exception as e:
        logger.error(f"Error generating minor tags: {str(e)}")
        return []


# =============================================================================
# ARQ TASKS for Admin Actions
# =============================================================================


async def task_categorize_minor_tags(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
) -> None:
    """
    Task to categorize questions and save minor tags in Question.minor_tags field.
    """
    async with get_db_session_for_worker(ctx) as session:
        try:
            # Get questions to categorize
            if question_ids is None:
                stmt = (
                    select(Question)
                    .options(selectinload(Question.choices))
                    .where(Question.is_active == True)
                )
            else:
                stmt = (
                    select(Question)
                    .options(selectinload(Question.choices))
                    .where(Question.id.in_(question_ids))
                    .where(Question.is_active == True)
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

                except Exception as e:
                    logger.error(f"Error categorizing question {question.id}: {str(e)}")
                    continue

            # Commit all changes
            await session.commit()
            logger.info(
                f"Completed minor tags categorization for {len(questions)} questions"
            )

        except Exception as e:
            logger.error(f"Error in task_categorize_minor_tags: {str(e)}")
            raise


async def task_categorize_major_tags(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
) -> None:
    """
    Task to classify question subjects and save major tags in Question.major_tags field.
    """
    async with get_db_session_for_worker(ctx) as session:
        try:
            # Get questions to categorize
            if question_ids is None:
                stmt = (
                    select(Question)
                    .options(selectinload(Question.choices))
                    .where(Question.is_active == True)
                )
            else:
                stmt = (
                    select(Question)
                    .options(selectinload(Question.choices))
                    .where(Question.id.in_(question_ids))
                    .where(Question.is_active == True)
                )

            result = await session.execute(stmt)
            questions: list[Question] = list(result.scalars())

            logger.info(
                f"Starting major tag classification for {len(questions)} questions"
            )

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

                except Exception as e:
                    logger.error(f"Error classifying question {question.id}: {str(e)}")
                    continue

            # Commit all changes
            await session.commit()
            logger.info(
                f"Completed major tag classification for {len(questions)} questions"
            )

        except Exception as e:
            logger.error(f"Error in task_categorize_major_tags: {str(e)}")
            raise


async def task_generate_question_answers(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
) -> None:
    """
    Task to generate answers for questions and save in Question.answer_content_blocks field.
    """
    async with get_db_session_for_worker(ctx) as session:
        try:
            # Get questions to generate answers for
            if question_ids is None:
                stmt = (
                    select(Question)
                    .options(selectinload(Question.choices))
                    .where(Question.is_active == True)
                )
            else:
                stmt = (
                    select(Question)
                    .options(selectinload(Question.choices))
                    .where(Question.id.in_(question_ids))
                    .where(Question.is_active == True)
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

                except Exception as e:
                    logger.error(
                        f"Error generating answer for question {question.id}: {str(e)}"
                    )
                    continue

            # Commit all changes
            await session.commit()
            logger.info(f"Completed answer generation for {len(questions)} questions")

        except Exception as e:
            logger.error(f"Error in task_generate_question_answers: {str(e)}")
            raise


async def task_analyze_question_quantitativeness(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
) -> None:
    """
    Task to analyze if questions require paper and save in Question.is_quantitative field.
    """
    async with get_db_session_for_worker(ctx) as session:
        try:
            # Get questions to analyze
            if question_ids is None:
                stmt = (
                    select(Question)
                    .options(selectinload(Question.choices))
                    .where(Question.is_active == True)
                )
            else:
                stmt = (
                    select(Question)
                    .options(selectinload(Question.choices))
                    .where(Question.id.in_(question_ids))
                    .where(Question.is_active == True)
                )

            result = await session.execute(stmt)
            questions: list[Question] = list(result.scalars())

            logger.info(
                f"Starting quantitative analysis for {len(questions)} questions"
            )

            # Process each question
            for question in questions:
                try:
                    # Get complete question text with choices
                    question_text_with_choices = (
                        question.question_text_with_choices_text
                    )

                    if not question_text_with_choices:
                        logger.info(
                            f"Skipping question without text or choices: {question.id}"
                        )
                        question.is_quantitative = False
                        continue

                    # Get question image URLs
                    image_urls = await get_question_image_urls(session, question)

                    # Analyze quantitativeness
                    analysis = await is_quantitative(
                        question_text_with_choices, image_urls
                    )

                    # Save to question
                    question.is_quantitative = analysis.requires_paper

                    logger.info(
                        f"Analyzed question {question.id}: requires_paper={analysis.requires_paper}"
                    )

                except Exception as e:
                    logger.error(f"Error analyzing question {question.id}: {str(e)}")
                    continue

            # Commit all changes
            await session.commit()
            logger.info(
                f"Completed quantitative analysis for {len(questions)} questions"
            )

        except Exception as e:
            logger.error(f"Error in task_analyze_question_quantitativeness: {str(e)}")
            raise


async def task_compute_question_embeddings(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
) -> None:
    """
    Asynchronously computes and stores embeddings for questions.

    Args:
        ctx: ARQ worker context
        question_ids: List of question IDs to process, None means all questions
    """
    async with get_db_session_for_worker(ctx) as session:
        if question_ids is None:
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.is_active == True)
            )
        else:
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.id.in_(question_ids))
                .where(Question.is_active == True)
            )

        # Execute the query
        result = await session.execute(stmt)
        questions: list[Question] = list(result.scalars())

        if not questions:
            logger.info("No questions found for embedding computation")
            return

        # Build texts for embedding
        texts_for_embedding: list[str] = []
        for question in questions:
            text_content = "\n".join(
                content.text
                for block in question.content_blocks
                if hasattr(block, "block_type") and block.block_type == "text"
                for content in block.content
                if hasattr(content, "text")
            )
            choices_text = "\n".join(choice.text for choice in question.choices)
            texts_for_embedding.append(f"{text_content}\n\n{choices_text}")

        # Compute embeddings
        embeddings = await openai_utils.compute_embedding(texts_for_embedding)

        # Update questions with embeddings
        for question, embedding in zip(questions, embeddings):
            question.embedding = embedding

        logger.info(f"Computed embeddings for {len(questions)} questions")


async def task_categorize_questions(
    ctx: dict[str, Any],
    question_ids: list[int] | None,
    temperature: float = 0.3,
) -> None:
    """
    Asynchronously categorizes questions using TAGS approach.

    Args:
        ctx: ARQ worker context
        question_ids: List of question IDs to process, None means all questions
        temperature: Temperature for AI model
    """
    async with get_db_session_for_worker(ctx) as session:
        if question_ids is None:
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.is_active == True)
            )
        else:
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.id.in_(question_ids))
                .where(Question.is_active == True)
            )

        result = await session.execute(stmt)
        questions: list[Question] = list(result.scalars())

        if not questions:
            logger.info("No questions found for categorization")
            return

        categorized_count = 0

        for question in questions:
            try:
                # Extract question text and choices
                question_text = question.question_text
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
                    question_text_with_choices, temperature, image_urls
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

            except Exception as e:
                logger.error(f"Error categorizing question {question.id}: {str(e)}")
                continue

        logger.info(f"Categorized {categorized_count} questions")
