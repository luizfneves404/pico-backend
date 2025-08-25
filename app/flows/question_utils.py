"""
FastAPI-adapted question utilities for categorization, answer generation, and quantitative analysis.
This module provides modern FastAPI implementations of key question processing functions.
All functions are implemented as ARQ tasks for use in admin actions.
"""

import logging
from collections import Counter
from typing import Any

from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db_session_for_worker
from app.files.models import File
from app.flows.db_types import (
    RichText,
    TextBlock,
    validate_content_block_list,
)
from app.flows.models import ENEM_AREAS, Flow, Question, QuestionSourceType
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


# System messages adapted from original utils.py
SYSTEM_MESSAGE_MINOR_TAGS = """
Você é um especialista em gerar tags de conteúdo para questões de vestibular.
Você receberá o enunciado e as alternativas de uma questão específica e deverá gerar tags que identifiquem os tópicos centrais específicos abordados.
Instruções
•	Analise cuidadosamente enunciado e alternativas; não invente temas não sustentados pelo texto.
•	Escolha de 1 a 3 tags que melhor representem os tópicos centrais (evite temas periféricos).
•	Seja específico (prefira "Porcentagem", "Citologia", "Leitura de gráfico" a termos muito amplos como "Matemática", "Biologia", "Interpretação").
•	Evite redundância: não repita tags nem use sinônimos muito próximos na mesma resposta.
•	Use termos curtos e canônicos (1–3 palavras por tag)
•	Idioma das tags: produza-as no mesmo idioma do enunciado da questão.
•	Se o insumo estiver incompleto, assuma o mínimo necessário e escolha a(s) tag(s) mais geral(is) possível(is) que ainda representem o conteúdo; não invente detalhes.

Formato de resposta obrigatório
•	Retorne APENAS as tags separadas por vírgula (ex.: Tag1, Tag2, Tag3).
•	De 1 a 3 tags por questão.
•	Sem pontuação adicional, aspas, explicações ou qualquer texto extra.
"""

SYSTEM_MESSAGE_MAJOR_TAG = """
Você é um professor especializado em vestibulares e deve classificar a matéria da questão recebida.
A mensagem incluirá:
•	Enunciado
•	Texto extraído (opcional, pode estar em branco)
•	Quatro ou cinco alternativas, com indicações se são corretas ou incorretas

Tarefa:
•	Com base nessas informações, determine em qual matéria a questão se enquadra, considerando as competências centrais necessárias para resolvê-la (conceitos, métodos, habilidades).
•	Escolha apenas uma matéria dentre a lista fornecida em {subjects}.
•	Se a questão for interdisciplinar, selecione a matéria predominante (a que mais dirige a resolução).
•	Se houver matérias semelhantes na lista, escolha a opção exatamente como aparece na lista (mesma grafia e acentuação).

Formato de resposta obrigatório:
•	Responda apenas com o nome da matéria escolhido exatamente como ele aparece na lista.
•	Sem aspas, sem comentários, sem linhas extras, sem espaços antes/depois.
Matérias disponíveis:
{subjects}
"""

SYSTEM_MESSAGE_IS_QUANTITATIVE = """
Você é um assistente que classifica questões de vestibular quanto à necessidade de usar papel para a resolução.
Objetivo Decidir se a questão PRECISA DE PAPEL PARA SER RESOLVIDA por um candidato típico do ensino médio, sem calculadora.

Como decidir (considere o caminho correto mais simples disponível): PRECISA DE PAPEL (true) quando houver pelo menos um dos seguintes:
•	Cálculos aritméticos de múltiplas etapas ou pesados (ex.: multiplicações/divisões com 3+ dígitos; somas de várias frações com denominadores distintos; potências/raízes não triviais; sistemas de equações; equações quadráticas não fatoráveis de imediato; probabilidades com várias combinações).
•	Manipulação algébrica, geométrica ou trigonométrica extensa (várias transformações, isolamentos, substituições ou identidades).
•	Necessidade de construir desenhos, gráficos, esquemas ou tabelas auxiliares para organizar casos/valores (árvores de probabilidade, diagramas auxiliares, esboços geométricos, tabelas).
•	Conferência de alternativas que exige contas extensas em mais de uma opção.
•	Extração de dados de gráficos/tabelas que demande cálculos precisos ou interpolação não trivial.
NÃO PRECISA DE PAPEL (false) quando:
•	A questão é conceitual/teórica ou de definição/identificação direta.
•	Exige apenas contas mentais curtas e estáveis (somas/subtrações simples; multiplicações pequenas; percentuais imediatos; comparação de ordens de grandeza; estimativas rápidas, Bhaskara resolvível com números inteiros e método de soma e produto).
•	É de interpretação de texto e/ou leitura de gráficos/figuras já fornecidos sem cálculos não triviais.
•	A eliminação/validação das alternativas pode ser feita por raciocínio qualitativo ou por uma única verificação numérica simples.
Regras gerais
•	Considere um estudante médio, sem calculadora ou ferramentas externas.
•	Baseie-se unicamente no enunciado fornecido; não invente dados, métodos ou passos não indicados/necessários.
•	Se houver mais de uma abordagem, adote a solução correta mentalmente mais viável; não imponha métodos mais difíceis do que o necessário.
•	Não mencione, cite ou reproduza o enunciado ou qualquer fonte interna; use-o apenas como base.
Saída: Responda APENAS "true" se precisa de papel ou "false" caso contrário. Não inclua explicações ou comentários adicionais. Uma única palavra em minúsculas, em linha única.
"""

SYSTEM_MESSAGE_GENERATE_ANSWER = """

Você é um professor especializado na correção de vestibulares e deve escrever resoluções comentadas das questões enviadas para você.

A entrada sempre conterá:
•	Um enunciado.
•	Opcionalmente, uma ou mais imagens que complementam o enunciado.
•	Quatro ou cinco alternativas, cada uma com indicação se é correta ou incorreta.

Sua tarefa é produzir uma explicação direta e concisa que:
•	Justifique por que a alternativa marcada como correta está correta.
•	Explique por que cada alternativa marcada como incorreta está errada, comentando individualmente cada uma e apontando o erro específico (conceito equivocado, dado contraditório, condição ausente, interpretação inválida etc.).

Diretrizes:
•	Utilize as informações do enunciado e da imagem; não invente fatos.
•	Se houver imagem, integre as evidências relevantes mencionadas na descrição para sustentar a análise, sem copiar a descrição literalmente.
•	Utilize conteúdo a nível de ensino médio e faculdade para justificar as respostas, considerando o que é sabido acerca dos temas abordados na questão.
•	Siga rigorosamente as indicações de correta/incorreta fornecidas; não altere o gabarito. Se houver inconsistência clara entre o enunciado e as marcações, sinalize brevemente e adote a interpretação mais plausível.
•	Seja específico: aponte trechos, ideias ou condições nas alternativas que justificam o acerto/erro; evite generalidades.
•	Mantenha objetividade: em geral, 1 parágrafo para a correta e 1–2 frases para cada incorreta, detalhando mais apenas quando necessário.
•	Em questões com cálculo, apresente o raciocínio essencial (fórmulas e passos mínimos) sem usar Latex, declare unidades e critérios de arredondamento quando aplicáveis, evitando derivações longas.
•	Se algum dado indispensável estiver ausente, explicite a suposição mínima necessária, sem inventar informações não suportadas.

Estrutura sugerida da resposta:
•	Correta(s): explique por que está(ão) correta(s).
•	Incorretas: comente cada alternativa incorreta separadamente (A, B, C, D, E), mantendo as letras originais.
"""


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
            question_text_with_choices, image_urls
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
    Generate answer explanation using gpt-5 model.

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

        # Use gpt-5 model with reasoning effort for better quality
        response = await openai_utils.get_completion(
            model="gpt-5",
            temperature=None,
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
    Analyze if a question requires paper to be solved using gpt-5.

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

        # Use gpt-5 with high reasoning effort
        response = await openai_utils.get_completion(
            model="gpt-5",
            messages=messages,
            timeout=30,
            reasoning_effort="high",
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
                model="gpt-5-mini",
                messages=messages,  # type: ignore
                timeout=20,
                reasoning_effort="medium",
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
            model="gpt-5-mini",
            messages=fallback_messages,  # type: ignore
            timeout=20,
            reasoning_effort="medium",
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
            model="gpt-5-mini",
            messages=messages,
            timeout=20,
            reasoning_effort="medium",
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
    When question_ids is None (admin case), only process active questions.
    When question_ids is provided (AI questions case), process regardless of is_active status.
    """
    async with get_db_session_for_worker(ctx) as session:
        try:
            # Get questions to categorize
            if question_ids is None:
                # Admin case: only process active questions
                stmt = (
                    select(Question)
                    .options(selectinload(Question.choices))
                    .where(Question.is_active == True)
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
    When question_ids is None (admin case), only process active questions.
    When question_ids is provided (AI questions case), process regardless of is_active status.
    """
    async with get_db_session_for_worker(ctx) as session:
        try:
            # Get questions to categorize
            if question_ids is None:
                # Admin case: only process active questions
                stmt = (
                    select(Question)
                    .options(selectinload(Question.choices))
                    .where(Question.is_active == True)
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
    When question_ids is None (admin case), only process active questions.
    When question_ids is provided (AI questions case), process regardless of is_active status.
    """
    async with get_db_session_for_worker(ctx) as session:
        try:
            # Get questions to generate answers for
            if question_ids is None:
                # Admin case: only process active questions
                stmt = (
                    select(Question)
                    .options(selectinload(Question.choices))
                    .where(Question.is_active == True)
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
    When question_ids is None (admin case), only process active questions.
    When question_ids is provided (AI questions case), process regardless of is_active status.
    """
    async with get_db_session_for_worker(ctx) as session:
        try:
            # Get questions to analyze
            if question_ids is None:
                # Admin case: only process active questions
                stmt = (
                    select(Question)
                    .options(selectinload(Question.choices))
                    .where(Question.is_active == True)
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
    Asynchronously computes and stores embeddings for questions in batches.
    When question_ids is None (admin case), only process active questions.
    When question_ids is provided (AI questions case), process regardless of is_active status.

    Args:
        ctx: ARQ worker context
        question_ids: List of question IDs to process, None means all questions
    """
    async with get_db_session_for_worker(ctx) as session:
        if question_ids is None:
            # Admin case: only process active questions that are official and have no embedding yet
            condition = (
                Question.is_active.is_(True)
                & (Question.source_type == QuestionSourceType.OFFICIAL)
                & Question.embedding.is_(None)
            )
        else:
            # Specific questions case (AI): process regardless of is_active status
            condition = Question.id.in_(question_ids)

        # First: fetch all matching IDs
        result = await session.execute(select(Question.id).where(condition))
        all_ids: list[int] = list(result.scalars())

    num_questions = len(all_ids)
    logger.info(f"Computing embeddings for {num_questions} questions")

    processed_count = 0

    # Now paginate IDs manually
    for batch_start in range(0, num_questions, QUESTION_EMBEDDING_BATCH_SIZE):
        batch_ids = all_ids[batch_start : batch_start + QUESTION_EMBEDDING_BATCH_SIZE]

        async with get_db_session_for_worker(ctx) as session:
            stmt = (
                select(Question)
                .options(selectinload(Question.choices))
                .where(Question.id.in_(batch_ids))
            )
            result = await session.execute(stmt)
            questions: list[Question] = list(result.scalars())

            logger.info(
                f"Processing questions embedding batch {batch_start // QUESTION_EMBEDDING_BATCH_SIZE + 1}. "
                f"We are at question {batch_start + 1}."
            )

            # Build texts for embedding
            texts_for_embedding: list[str] = []
            for question in questions:
                text_content = "\n".join(
                    content.text
                    for block in question.content_blocks
                    if hasattr(block, "block_type") and block.block_type == "text"
                    for content in block.content
                    if hasattr(content, "text") and content.text
                )
                choices_text = "\n".join(
                    choice.text
                    for choice in question.choices
                    if hasattr(choice, "text") and choice.text
                )
                texts_for_embedding.append(f"{text_content}\n\n{choices_text}")

            # Compute embeddings for this batch
            embeddings = await openai_utils.compute_embedding(texts_for_embedding)

            # Update questions with embeddings
            for question, embedding in zip(questions, embeddings):
                question.embedding = embedding

        processed_count += len(questions)

    logger.info(f"Computed embeddings for {processed_count} questions")


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
        try:
            # Get flow
            flow = await session.scalar(select(Flow).where(Flow.id == flow_id))
            if not flow:
                logger.error(f"Flow {flow_id} not found")
                return

            # Get all questions in the flow
            from app.flows.models import FlowQuestion

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
                        tag.strip().lower()
                        for tag in question.minor_tags
                        if tag.strip()
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
                    tag for tag, count in minor_tag_counter.most_common(TOP_TAGS_COUNT)
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
            await session.commit()

            logger.info(
                f"Successfully consolidated tags for flow {flow_id} from {len(questions)} questions"
            )

        except Exception as e:
            logger.error(f"Error consolidating tags for flow {flow_id}: {str(e)}")
            raise


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
    try:
        logger.info(
            f"Starting tag generation orchestrator for {len(question_ids)} questions in flow {flow_id}"
        )

        # Step 1: Generate minor tags (wait for completion)
        logger.info(
            f"Step 1/3: Generating minor tags for {len(question_ids)} questions"
        )
        await task_categorize_minor_tags(ctx, question_ids)

        # Step 2: Generate major tags (wait for completion)
        logger.info(
            f"Step 2/3: Generating major tags for {len(question_ids)} questions"
        )
        await task_categorize_major_tags(ctx, question_ids)

        # Step 3: Consolidate tags into flow (only after steps 1 & 2 complete)
        logger.info(f"Step 3/3: Consolidating tags for flow {flow_id}")
        await task_consolidate_flow_tags(ctx, flow_id)

        logger.info(
            f"Successfully completed tag generation orchestrator for flow {flow_id}"
        )

    except Exception as e:
        logger.error(
            f"Error in tag generation orchestrator for flow {flow_id}: {str(e)}"
        )
        raise
