import json
from collections.abc import Sequence
from typing import Any, ClassVar

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqladmin import action
from sqladmin.fields import JSONField
from sqlalchemy import Select
from sqlalchemy.orm import selectinload
from wtforms import Field, widgets
from wtforms.validators import Optional

from app.arq_client import enqueue_job
from app.flows.db_types import (
    ContentBlockDB,
    validate_content_block_list,
)
from app.flows.models import (
    Campaign,
    Choice,
    Exam,
    Flow,
    FlowElement,
    FlowFeedScore,
    FlowFeedScoreGroupType,
    FlowQuestion,
    FlowQuestionUser,
    FlowTranscriptionBlock,
    FlowUserFeed,
    OfficialQuestionSource,
    Question,
    QuestionAnswerType,
    QuestionArea,
    QuestionDifficulty,
    QuestionSourceType,
)
from app.shared.admin import MODEL_ATTR, CustomModelView


class ContentBlocksField(JSONField):
    def _value(self) -> str:
        if self.raw_data:
            return self.raw_data[0]
        elif self.data:
            return json.dumps(
                [block.model_dump(mode="json") for block in self.data],
                indent=4,
                ensure_ascii=False,
            )
        else:
            return "[]"

    def process_formdata(self, valuelist: list[str]) -> None:
        if valuelist:
            value = valuelist[0]

            # allow saving blank field as empty list
            if not value:
                self.data = []
                return

            try:
                self.data = validate_content_block_list(json.loads(value))
            except ValueError as e:
                raise ValueError(self.gettext(f"Invalid JSON: {e}")) from e


class TagsTextAreaField(Field):
    widget = widgets.TextArea()

    def _value(self):
        # Render list as a comma-separated string
        if self.data:
            return ", ".join(self.data)
        return ""

    def process_formdata(self, valuelist):
        if valuelist:
            # Split by comma, strip whitespace
            self.data = [v.strip() for v in valuelist[0].split(",") if v.strip()]
        else:
            self.data = []


class FlowAdmin(CustomModelView, model=Flow):
    icon = "fa-solid fa-stream"

    column_list = (
        Flow.id,
        Flow.code,
        Flow.title,
        Flow.created_by,
        Flow.flow_input_type,
        Flow.difficulty,
        Flow.question_answer_type,
        Flow.source_type,
        Flow.max_num_questions,
        Flow.is_ready,
        Flow.has_quantitative_questions,
        Flow.created_at,
    )
    column_searchable_list = (
        Flow.title,
        Flow.input_topic,
        Flow.major_tags,
        Flow.minor_tags,
    )
    column_sortable_list = (
        Flow.id,
        Flow.title,
        Flow.created_at,
        Flow.difficulty,
        Flow.flow_input_type,
        Flow.source_type,
    )
    column_details_list = (
        Flow.id,
        Flow.code,
        Flow.title,
        Flow.created_by,
        Flow.cover_image,
        Flow.action_link,
        Flow.action_text,
        Flow.max_num_questions,
        Flow.difficulty,
        Flow.question_answer_type,
        Flow.source_type,
        Flow.flow_input_type,
        Flow.input_topic,
        Flow.major_tags,
        Flow.minor_tags,
        Flow.is_ready,
        "num_total_questions",
        "num_total_elements",
        "num_total_answers",
        Flow.has_quantitative_questions,
        Flow.created_at,
    )

    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        "num_total_questions": "Total Questions",
        "num_total_elements": "Total Elements",
        "num_total_answers": "Total Answers",
        Flow.created_by: "Created By",
        Flow.cover_image: "Cover Image",
    }

    form_columns: ClassVar[str | Sequence[MODEL_ATTR]] = [
        Flow.title,
        Flow.created_by,
        Flow.cover_image,
        Flow.action_link,
        Flow.action_text,
        Flow.max_num_questions,
        Flow.difficulty,
        Flow.question_answer_type,
        Flow.source_type,
        Flow.flow_input_type,
        Flow.input_topic,
        Flow.major_tags,
        Flow.minor_tags,
        Flow.is_ready,
        Flow.has_quantitative_questions,
    ]

    form_args: ClassVar[dict[str, Any]] = {
        "major_tags": {
            "validators": [Optional()],
            "description": "Digite as tags principais separadas por vírgula (ex: matemática, álgebra, geometria)",
        },
        "minor_tags": {
            "validators": [Optional()],
            "description": "Digite as tags secundárias separadas por vírgula (ex: básico, intermediário, avançado)",
        },
    }

    form_overrides: ClassVar[dict[str, type[Field]]] = {
        "major_tags": TagsTextAreaField,
        "minor_tags": TagsTextAreaField,
    }

    def list_query(self, request: Request) -> Select[tuple[Flow]]:
        stmt: Select[tuple[Flow]] = super().list_query(request)  # type: ignore

        return stmt.options(
            selectinload(Flow.created_by),
            selectinload(Flow.cover_image),
        )

    def details_query(self, request: Request) -> Select[tuple[Flow]]:
        stmt: Select[tuple[Flow]] = super().details_query(request)  # type: ignore

        return stmt.options(
            selectinload(Flow.created_by),
            selectinload(Flow.cover_image),
            selectinload(Flow.elements.of_type(FlowQuestion)).options(
                selectinload(FlowQuestion.question).options(
                    selectinload(Question.choices),
                    selectinload(Question.source_user),
                    selectinload(Question.official_source),
                ),
                selectinload(FlowQuestion.flow_question_users),
            ),
            selectinload(Flow.elements.of_type(FlowElement)),
        )


class FlowTranscriptionBlockAdmin(CustomModelView, model=FlowTranscriptionBlock):
    icon = "fa-solid fa-file-text"

    column_list = (
        FlowTranscriptionBlock.id,
        FlowTranscriptionBlock.flow_id,
        FlowTranscriptionBlock.block_number,
        FlowTranscriptionBlock.title,
        FlowTranscriptionBlock.created_at,
    )
    column_searchable_list = (
        FlowTranscriptionBlock.flow_id,
        FlowTranscriptionBlock.title,
        FlowTranscriptionBlock.block_text,
    )
    column_sortable_list = (
        FlowTranscriptionBlock.id,
        FlowTranscriptionBlock.flow_id,
        FlowTranscriptionBlock.block_number,
        FlowTranscriptionBlock.created_at,
    )
    column_details_list = (
        FlowTranscriptionBlock.id,
        FlowTranscriptionBlock.flow_id,
        FlowTranscriptionBlock.block_number,
        FlowTranscriptionBlock.title,
        FlowTranscriptionBlock.block_text,
        FlowTranscriptionBlock.created_at,
    )

    form_columns = (
        FlowTranscriptionBlock.flow_id,
        FlowTranscriptionBlock.block_number,
        FlowTranscriptionBlock.title,
        FlowTranscriptionBlock.block_text,
    )


class FlowElementAdmin(CustomModelView, model=FlowElement):
    icon = "fa-solid fa-list"

    column_list = (
        FlowElement.id,
        FlowElement.flow_id,
        FlowElement.element_type,
        FlowElement.order,
        FlowElement.question_id,
        FlowElement.created_at,
    )
    column_searchable_list = (
        FlowElement.flow_id,
        FlowElement.question_id,
        FlowElement.element_type,
    )
    column_sortable_list = (
        FlowElement.id,
        FlowElement.flow_id,
        FlowElement.order,
        FlowElement.created_at,
    )
    column_details_list = (
        FlowElement.id,
        FlowElement.flow_id,
        FlowElement.element_type,
        FlowElement.order,
        FlowElement.question_id,
        FlowElement.created_at,
    )

    form_columns = (
        FlowElement.flow,
        FlowElement.order,
        FlowElement.element_type,
        FlowElement.question_id,
    )


class QuestionImportSchema(BaseModel):
    id: int | None = None
    content_blocks: list[ContentBlockDB]
    answer_content_blocks: list[ContentBlockDB] = []
    major_tags: list[str] = []
    minor_tags: list[str] = []
    difficulty: QuestionDifficulty
    source_type: QuestionSourceType = QuestionSourceType.OFFICIAL
    answer_type: QuestionAnswerType
    is_active: bool = True
    is_quantitative: bool
    official_source_id: int | None
    source_user_id: int | None = None
    parameter_a: float | None = None
    parameter_b: float | None = None
    parameter_c: float | None = None


class QuestionAdmin(CustomModelView, model=Question):
    icon = "fa-solid fa-question-circle"

    column_list: ClassVar[str | Sequence[MODEL_ATTR]] = (
        Question.id,
        Question.created_at,
        "question_truncated_text",
        Question.major_tags,
        Question.minor_tags,
        Question.source_type,
        Question.difficulty,
        Question.answer_type,
        Question.is_quantitative,
        Question.is_active,
        "has_embedding",
    )
    column_searchable_list: ClassVar[str | Sequence[MODEL_ATTR]] = (
        Question.content_blocks,
        Question.major_tags,
        Question.minor_tags,
    )
    column_sortable_list: ClassVar[str | Sequence[MODEL_ATTR]] = (
        Question.id,
        Question.created_at,
        Question.is_quantitative,
        Question.difficulty,
        Question.source_type,
        Question.is_active,
        "has_embedding",
    )
    column_details_list: ClassVar[str | Sequence[MODEL_ATTR]] = (
        Question.id,
        Question.content_blocks,
        Question.is_active,
        Question.is_quantitative,
        Question.major_tags,
        Question.minor_tags,
        Question.difficulty,
        Question.parameter_a,
        Question.parameter_b,
        Question.parameter_c,
        Question.answer_content_blocks,
        Question.source_type,
        Question.official_source,
        Question.source_user,
        Question.answer_type,
        Question.created_at,
    )

    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        Question.is_quantitative: "Quantitative?",
        Question.is_active: "Active?",
        Question.source_type: "Source Type",
        Question.answer_type: "Answer Type",
        Question.official_source: "Official Source",
        Question.source_user: "Source User",
        "has_embedding": "Has Embedding?",
    }

    form_excluded_columns = (
        "created_at",
        "embedding",
        "flows",
        "flow_questions",
    )

    form_ajax_refs: ClassVar[dict[str, dict[str, Any]]] = {
        "choices": {
            "fields": ("text", "is_correct"),
            "order_by": "id",
        }
    }

    form_overrides: ClassVar[dict[str, type[Field]]] = {
        "content_blocks": ContentBlocksField,
        "answer_content_blocks": ContentBlocksField,
        "major_tags": TagsTextAreaField,
        "minor_tags": TagsTextAreaField,
    }

    form_widget_args: ClassVar[dict[str, dict[str, Any]]] = {
        "content_blocks": {
            "rows": 30,
        },
        "answer_content_blocks": {
            "rows": 30,
        },
    }

    can_import = True

    import_schema = QuestionImportSchema

    import_template_data: ClassVar = {
        "id": 99999,
        "content_blocks": [
            {
                "block_type": "text",
                "content": [
                    {
                        "text": "Digite o texto da pergunta aqui",
                        "bold": False,
                        "italic": False,
                        "underline": False,
                        "strikethrough": False,
                    }
                ],
                "style": "paragraph",
            },
            {
                "block_type": "image",
                "image_id": 1,
                "alt": "texto alternativo para a imagem",
            },
        ],
        "answer_content_blocks": [
            {
                "block_type": "text",
                "content": [
                    {
                        "text": "Digite o texto do gabarito aqui",
                        "bold": False,
                        "italic": False,
                        "underline": False,
                        "strikethrough": False,
                    }
                ],
                "style": "paragraph",
            },
            {
                "block_type": "image",
                "image_id": 1,
                "alt": "texto alternativo para a imagem",
            },
        ],
        "difficulty": QuestionDifficulty.MEDIUM,
        "source_type": QuestionSourceType.OFFICIAL,
        "answer_type": QuestionAnswerType.MULTIPLE_CHOICE,
        "is_active": True,
        "is_quantitative": False,
        "major_tags": ["matemática", "álgebra", "geometria"],
        "minor_tags": ["básico", "intermediário", "avançado"],
        "official_source_id": 1,
        "source_user_id": None,
        "parameter_a": None,
        "parameter_b": None,
        "parameter_c": None,
    }

    @action(
        name="compute_embeddings",
        label="Computar embeddings",
        confirmation_message="Tem certeza que quer computar embeddings para as perguntas selecionadas?",
        add_in_detail=False,
        add_in_list=True,
    )
    async def compute_question_embeddings(self, request: Request) -> RedirectResponse:
        """Compute embeddings for all questions in the list."""
        pks_str = request.query_params.get("pks", "")

        # Build the base statement
        if pks_str == "__all__":
            pks = None
        else:
            try:
                pks = [int(pk) for pk in pks_str.split(",")]
                if not pks:
                    # Redirect if no pks are provided
                    referer = request.headers.get("Referer")
                    return RedirectResponse(
                        referer or request.url_for("admin:list", identity=self.identity)
                    )
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail="Invalid primary key format."
                ) from e

        await enqueue_job(
            "task_compute_question_embeddings",
            question_ids=pks,
        )

        # Redirect back
        referer = request.headers.get("Referer")
        return RedirectResponse(
            referer or request.url_for("admin:list", identity=self.identity)
        )

    @action(
        name="recompute_embeddings",
        label="Recomputar embeddings",
        confirmation_message="Tem certeza que quer recomputar embeddings para as perguntas selecionadas? Isso irá sobrescrever embeddings existentes.",
        add_in_detail=False,
        add_in_list=True,
    )
    async def recompute_question_embeddings(self, request: Request) -> RedirectResponse:
        """Recompute embeddings for all questions in the list, overriding existing ones."""
        pks_str = request.query_params.get("pks", "")

        # Build the base statement
        if pks_str == "__all__":
            pks = None
        else:
            try:
                pks = [int(pk) for pk in pks_str.split(",")]
                if not pks:
                    # Redirect if no pks are provided
                    referer = request.headers.get("Referer")
                    return RedirectResponse(
                        referer or request.url_for("admin:list", identity=self.identity)
                    )
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail="Invalid primary key format."
                ) from e

        await enqueue_job(
            "task_recompute_question_embeddings",
            question_ids=pks,
        )

        # Redirect back
        referer = request.headers.get("Referer")
        return RedirectResponse(
            referer or request.url_for("admin:list", identity=self.identity)
        )

    @action(
        name="categorize_minor_tags",
        label="Categorizar minor tags",
        confirmation_message="Tem certeza que quer categorizar minor tags das perguntas selecionadas?",
        add_in_detail=False,
        add_in_list=True,
    )
    async def categorize_minor_tags(self, request: Request) -> RedirectResponse:
        """Categorize questions using TAGS approach - minor tags only."""
        pks_str = request.query_params.get("pks", "")

        if pks_str == "__all__":
            pks = None
        else:
            try:
                pks = [int(pk) for pk in pks_str.split(",")]
                if not pks:
                    referer = request.headers.get("Referer")
                    return RedirectResponse(
                        referer or request.url_for("admin:list", identity=self.identity)
                    )
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail="Invalid primary key format."
                ) from e

        await enqueue_job(
            "task_categorize_minor_tags",
            question_ids=pks,
        )

        referer = request.headers.get("Referer")
        return RedirectResponse(
            referer or request.url_for("admin:list", identity=self.identity)
        )

    @action(
        name="categorize_major_tags",
        label="Categorizar major tags",
        confirmation_message="Tem certeza que quer categorizar major tags (subjects) das perguntas selecionadas?",
        add_in_detail=False,
        add_in_list=True,
    )
    async def categorize_major_tags(self, request: Request) -> RedirectResponse:
        """Classify question subjects to determine major tags."""
        pks_str = request.query_params.get("pks", "")

        if pks_str == "__all__":
            pks = None
        else:
            try:
                pks = [int(pk) for pk in pks_str.split(",")]
                if not pks:
                    referer = request.headers.get("Referer")
                    return RedirectResponse(
                        referer or request.url_for("admin:list", identity=self.identity)
                    )
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail="Invalid primary key format."
                ) from e

        await enqueue_job(
            "task_categorize_major_tags",
            question_ids=pks,
        )

        referer = request.headers.get("Referer")
        return RedirectResponse(
            referer or request.url_for("admin:list", identity=self.identity)
        )

    @action(
        name="generate_answers",
        label="Gerar respostas",
        confirmation_message="Tem certeza que quer gerar respostas para as perguntas selecionadas?",
        add_in_detail=False,
        add_in_list=True,
    )
    async def generate_question_answers(self, request: Request) -> RedirectResponse:
        """Generate answers for questions using o3 model."""
        pks_str = request.query_params.get("pks", "")

        if pks_str == "__all__":
            pks = None
        else:
            try:
                pks = [int(pk) for pk in pks_str.split(",")]
                if not pks:
                    referer = request.headers.get("Referer")
                    return RedirectResponse(
                        referer or request.url_for("admin:list", identity=self.identity)
                    )
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail="Invalid primary key format."
                ) from e

        await enqueue_job(
            "task_generate_question_answers",
            question_ids=pks,
        )

        referer = request.headers.get("Referer")
        return RedirectResponse(
            referer or request.url_for("admin:list", identity=self.identity)
        )

    @action(
        name="analyze_quantitativeness",
        label="Analisar quantitatividade",
        confirmation_message="Tem certeza que quer analisar quantitatividade das perguntas selecionadas?",
        add_in_detail=False,
        add_in_list=True,
    )
    async def analyze_question_quantitativeness(
        self, request: Request
    ) -> RedirectResponse:
        """Analyze if questions require paper to solve."""
        pks_str = request.query_params.get("pks", "")

        if pks_str == "__all__":
            pks = None
        else:
            try:
                pks = [int(pk) for pk in pks_str.split(",")]
                if not pks:
                    referer = request.headers.get("Referer")
                    return RedirectResponse(
                        referer or request.url_for("admin:list", identity=self.identity)
                    )
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail="Invalid primary key format."
                ) from e

        await enqueue_job(
            "task_analyze_question_quantitativeness",
            question_ids=pks,
        )

        referer = request.headers.get("Referer")
        return RedirectResponse(
            referer or request.url_for("admin:list", identity=self.identity)
        )

    @action(
        name="fix_question_newlines",
        label="Corrigir quebras (\\n) no texto",
        confirmation_message="Tem certeza que quer substituir todos os literal \\n por espaço simples nas perguntas selecionadas?",
        add_in_detail=False,
        add_in_list=True,
    )
    async def fix_question_newlines(self, request: Request) -> RedirectResponse:
        """Fix literal "\\n" occurrences in question content blocks."""
        pks_str = request.query_params.get("pks", "")

        if pks_str == "__all__":
            pks = None
        else:
            try:
                pks = [int(pk) for pk in pks_str.split(",")]
                if not pks:
                    referer = request.headers.get("Referer")
                    return RedirectResponse(
                        referer or request.url_for("admin:list", identity=self.identity)
                    )
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail="Invalid primary key format."
                ) from e

        await enqueue_job(
            "task_fix_question_newlines",
            question_ids=pks,
        )

        referer = request.headers.get("Referer")
        return RedirectResponse(
            referer or request.url_for("admin:list", identity=self.identity)
        )

    async def to_orm_model(
        self, validated_data_list: list[QuestionImportSchema]
    ) -> list[Question]:
        """Convert Pydantic model to ORM model."""
        questions = [
            Question(
                difficulty=validated_data.difficulty,
                source_type=validated_data.source_type,
                answer_type=validated_data.answer_type,
                major_tags=validated_data.major_tags,
                minor_tags=validated_data.minor_tags,
                content_blocks=validated_data.content_blocks,
                answer_content_blocks=validated_data.answer_content_blocks,
                is_active=validated_data.is_active,
                is_quantitative=validated_data.is_quantitative,
                parameter_a=validated_data.parameter_a,
                parameter_b=validated_data.parameter_b,
                parameter_c=validated_data.parameter_c,
                embedding=None,
                official_source_id=validated_data.official_source_id,
                source_user_id=validated_data.source_user_id,
            )
            for validated_data in validated_data_list
        ]
        for question, validated_data in zip(
            questions, validated_data_list, strict=False
        ):
            if validated_data.id is not None:
                question.id = validated_data.id
        return questions

    def list_query(self, request: Request) -> Select[tuple[Question]]:
        stmt: Select[tuple[Question]] = super().list_query(request)  # type: ignore

        return stmt.options(
            selectinload(Question.official_source),
            selectinload(Question.source_user),
        )

    def form_edit_query(self, request: Request) -> Select[tuple[Question]]:
        stmt: Select[tuple[Question]] = super().form_edit_query(request)  # type: ignore

        return stmt.options(
            selectinload(Question.official_source).options(
                selectinload(OfficialQuestionSource.exam),
            ),
            selectinload(Question.source_user),
        )

    def details_query(self, request: Request) -> Select[tuple[Question]]:
        """Ensure related objects are eagerly loaded for the details view so answer content is available."""
        stmt: Select[tuple[Question]] = super().details_query(request)  # type: ignore

        return stmt.options(
            selectinload(Question.official_source).options(
                selectinload(OfficialQuestionSource.exam),
            ),
            selectinload(Question.source_user),
        )

    async def on_model_change(
        self,
        data: dict[str, Any],
        model: Question,
        is_created: bool,  # noqa: ARG002
        request: Request | None = None,  # noqa: ARG002
    ) -> None:
        """Process array fields before saving."""
        if "content_blocks" in data:
            if not data["content_blocks"]:
                data["content_blocks"] = []
            model.content_blocks = validate_content_block_list(data["content_blocks"])
        if "answer_content_blocks" in data:
            if not data["answer_content_blocks"]:
                data["answer_content_blocks"] = []
            model.answer_content_blocks = validate_content_block_list(
                data["answer_content_blocks"]
            )


class QuestionAreaAdmin(CustomModelView, model=QuestionArea):
    icon = "fa-solid fa-map"

    column_list = (
        QuestionArea.id,
        QuestionArea.name,
        QuestionArea.education_level,
        QuestionArea.country,
        QuestionArea.course,
        QuestionArea.created_at,
    )
    column_searchable_list = (
        QuestionArea.name,
        QuestionArea.tags,
    )
    column_sortable_list = (
        QuestionArea.id,
        QuestionArea.name,
        QuestionArea.created_at,
    )
    column_details_list = (
        QuestionArea.id,
        QuestionArea.name,
        QuestionArea.tags,
        QuestionArea.education_level,
        QuestionArea.country,
        QuestionArea.course,
        QuestionArea.created_at,
    )

    form_columns = (
        QuestionArea.name,
        QuestionArea.tags,
        QuestionArea.education_level,
        QuestionArea.country,
        QuestionArea.course,
    )

    form_args: ClassVar[dict[str, Any]] = {
        "tags": {
            "validators": [Optional()],
            "description": "Digite as tags separadas por vírgula (ex: matemática, básico, ensino médio)",
        },
    }


class ExamImportSchema(BaseModel):
    name: str
    country_id: int
    education_level_id: int
    course_id: int | None
    is_privileged: bool


class ExamAdmin(CustomModelView, model=Exam):
    icon = "fa-solid fa-clipboard-check"

    column_list = (
        Exam.id,
        Exam.name,
        Exam.country,
        Exam.education_level,
        Exam.course,
        Exam.is_privileged,
        Exam.created_at,
    )
    column_searchable_list = (Exam.name,)
    column_sortable_list = (
        Exam.id,
        Exam.name,
        Exam.created_at,
    )
    column_details_list = (
        Exam.id,
        Exam.name,
        Exam.country,
        Exam.education_level,
        Exam.course,
        Exam.is_privileged,
        Exam.created_at,
    )

    form_columns = (
        Exam.name,
        Exam.country,
        Exam.education_level,
        Exam.course,
        Exam.is_privileged,
    )

    can_import = True
    import_schema = ExamImportSchema
    import_template_data: ClassVar = {
        "name": "Exame Nacional do Ensino Médio",
        "country_id": 1,
        "education_level_id": 1,
        "course_id": 1,
        "is_privileged": False,
    }

    async def to_orm_model(
        self, validated_data_list: list[ExamImportSchema]
    ) -> list[Exam]:
        return [
            Exam(
                name=validated_data.name,
                country_id=validated_data.country_id,
                education_level_id=validated_data.education_level_id,
                course_id=validated_data.course_id,
                is_privileged=validated_data.is_privileged,
            )
            for validated_data in validated_data_list
        ]


class OfficialQuestionSourceImportSchema(BaseModel):
    exam_id: int
    year: int


class OfficialQuestionSourceAdmin(CustomModelView, model=OfficialQuestionSource):
    icon = "fa-solid fa-certificate"

    column_list = (
        OfficialQuestionSource.id,
        OfficialQuestionSource.exam,
        OfficialQuestionSource.year,
        OfficialQuestionSource.created_at,
    )
    column_searchable_list = (OfficialQuestionSource.year,)
    column_sortable_list = (
        OfficialQuestionSource.id,
        OfficialQuestionSource.year,
        OfficialQuestionSource.created_at,
    )
    column_details_list = (
        OfficialQuestionSource.id,
        OfficialQuestionSource.exam,
        OfficialQuestionSource.year,
        OfficialQuestionSource.created_at,
    )

    form_columns = (
        OfficialQuestionSource.exam,
        OfficialQuestionSource.year,
    )

    can_import = True
    import_schema = OfficialQuestionSourceImportSchema
    import_template_data: ClassVar = {
        "exam_id": 1,
        "year": 2024,
    }

    async def to_orm_model(
        self, validated_data_list: list[OfficialQuestionSourceImportSchema]
    ) -> list[OfficialQuestionSource]:
        return [
            OfficialQuestionSource(
                exam_id=validated_data.exam_id, year=validated_data.year
            )
            for validated_data in validated_data_list
        ]


class FlowUserFeedAdmin(CustomModelView, model=FlowUserFeed):
    icon = "fa-solid fa-rss"

    column_list = (
        FlowUserFeed.id,
        FlowUserFeed.user_id,
        FlowUserFeed.flow_id,
        FlowUserFeed.created_at,
    )
    column_searchable_list = (
        FlowUserFeed.user_id,
        FlowUserFeed.flow_id,
    )
    column_sortable_list = (
        FlowUserFeed.id,
        FlowUserFeed.user_id,
        FlowUserFeed.flow_id,
        FlowUserFeed.created_at,
    )
    column_details_list = (
        FlowUserFeed.id,
        FlowUserFeed.user_id,
        FlowUserFeed.flow_id,
        FlowUserFeed.created_at,
    )

    form_columns = (
        FlowUserFeed.user,
        FlowUserFeed.flow,
    )


class CampaignAdmin(CustomModelView, model=Campaign):
    icon = "fa-solid fa-bullhorn"

    column_list = (
        Campaign.id,
        Campaign.name,
        Campaign.campaign_type,
        Campaign.probability,
        Campaign.created_at,
    )
    column_searchable_list = (
        Campaign.name,
        Campaign.text,
        Campaign.campaign_type,
    )
    column_sortable_list = (
        Campaign.id,
        Campaign.name,
        Campaign.campaign_type,
        Campaign.probability,
        Campaign.created_at,
    )
    column_details_list = (
        Campaign.id,
        Campaign.name,
        Campaign.text,
        Campaign.external_link,
        Campaign.external_link_text,
        Campaign.image1,
        Campaign.image2,
        Campaign.probability,
        Campaign.campaign_type,
        Campaign.created_at,
    )

    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        Campaign.campaign_type: "Type",
        Campaign.external_link: "External Link",
        Campaign.external_link_text: "Link Text",
        Campaign.image1: "Image 1",
        Campaign.image2: "Image 2",
    }

    form_columns = (
        Campaign.name,
        Campaign.text,
        Campaign.external_link,
        Campaign.external_link_text,
        Campaign.image1,
        Campaign.image2,
        Campaign.probability,
        Campaign.campaign_type,
    )


class ChoiceImportSchema(BaseModel):
    question_id: int
    text: str | None
    is_correct: bool
    order: int
    image_id: int | None


class ChoiceAdmin(CustomModelView, model=Choice):
    icon = "fa-solid fa-check-circle"

    column_list = (
        Choice.id,
        Choice.question_id,
        Choice.text,
        Choice.is_correct,
        Choice.order,
        Choice.created_at,
    )
    column_searchable_list = (
        Choice.text,
        Choice.question_id,
    )
    column_sortable_list = (
        Choice.id,
        Choice.question_id,
        Choice.is_correct,
        Choice.order,
        Choice.created_at,
    )
    column_details_list = (
        Choice.id,
        Choice.question_id,
        Choice.text,
        Choice.image,
        Choice.is_correct,
        Choice.order,
        Choice.created_at,
    )

    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        "is_correct": "Correct?",
        "question_id": "Question",
    }

    form_columns = (
        Choice.question,
        Choice.text,
        Choice.image,
        Choice.is_correct,
        Choice.order,
    )

    can_import = True
    import_schema = ChoiceImportSchema
    import_template_data: ClassVar = {
        "question_id": 1,
        "text": "Digite o texto da opção aqui",
        "is_correct": True,
        "order": 1,
        "image_id": None,
    }

    async def to_orm_model(
        self, validated_data_list: list[ChoiceImportSchema]
    ) -> list[Choice]:
        return [
            Choice(
                question_id=validated_data.question_id,
                text=validated_data.text or "",
                is_correct=validated_data.is_correct,
                order=validated_data.order,
                image_id=validated_data.image_id,
            )
            for validated_data in validated_data_list
        ]


class FlowQuestionAdmin(CustomModelView, model=FlowQuestion):
    icon = "fa-solid fa-question"

    column_list: ClassVar[str | Sequence[MODEL_ATTR]] = (
        FlowQuestion.id,
        FlowQuestion.flow,
        FlowQuestion.question,
        FlowQuestion.order,
        "num_total_answers",
        FlowQuestion.created_at,
    )
    column_searchable_list = (
        FlowQuestion.flow,
        FlowQuestion.question,
    )
    column_sortable_list = (
        FlowQuestion.id,
        FlowQuestion.flow,
        FlowQuestion.order,
        FlowQuestion.created_at,
    )
    column_details_list: ClassVar[Sequence[MODEL_ATTR]] = (
        FlowQuestion.id,
        FlowQuestion.flow,
        FlowQuestion.question,
        FlowQuestion.order,
        "num_total_answers",
        FlowQuestion.created_at,
    )

    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        "num_total_answers": "Total Answers",
        "flow": "Flow",
        "question": "Question",
    }

    form_ajax_refs: ClassVar[dict[str, dict[str, Any]]] = {
        "question": {
            "fields": ("id",),
            "order_by": "id",
        }
    }

    form_columns = (
        FlowQuestion.flow,
        FlowQuestion.question,
        FlowQuestion.order,
    )

    def list_query(self, request: Request) -> Select[tuple[FlowQuestion]]:
        stmt: Select[tuple[FlowQuestion]] = super().list_query(request)  # type: ignore

        return stmt.options(
            selectinload(FlowQuestion.flow_question_users),
            selectinload(FlowQuestion.flow),
            selectinload(FlowQuestion.question),
        )

    def details_query(self, request: Request) -> Select[tuple[FlowQuestion]]:
        stmt: Select[tuple[FlowQuestion]] = super().details_query(request)  # type: ignore

        return stmt.options(
            selectinload(FlowQuestion.flow_question_users),
            selectinload(FlowQuestion.flow),
            selectinload(FlowQuestion.question),
        )


class FlowQuestionUserAdmin(CustomModelView, model=FlowQuestionUser):
    icon = "fa-solid fa-user-check"

    column_list = (
        FlowQuestionUser.id,
        FlowQuestionUser.flow_element_id,
        FlowQuestionUser.user_id,
        FlowQuestionUser.choice_id,
        FlowQuestionUser.grade,
        FlowQuestionUser.created_at,
    )
    column_searchable_list = (
        FlowQuestionUser.flow_element_id,
        FlowQuestionUser.user_id,
        FlowQuestionUser.submitted_text,
        FlowQuestionUser.feedback,
    )
    column_sortable_list = (
        FlowQuestionUser.id,
        FlowQuestionUser.created_at,
        FlowQuestionUser.grade,
    )
    column_details_list = (
        FlowQuestionUser.id,
        FlowQuestionUser.flow_element_id,
        FlowQuestionUser.user_id,
        FlowQuestionUser.choice,
        FlowQuestionUser.submitted_text,
        FlowQuestionUser.feedback,
        FlowQuestionUser.grade,
        FlowQuestionUser.created_at,
    )

    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        "flow_element_id": "Flow Element",
        "user_id": "User",
        "choice_id": "Choice",
        "submitted_text": "Submitted Text",
    }

    form_columns = (
        FlowQuestionUser.flow_element_id,
        FlowQuestionUser.user_id,
        FlowQuestionUser.choice_id,
        FlowQuestionUser.submitted_text,
        FlowQuestionUser.feedback,
        FlowQuestionUser.grade,
    )


class FlowFeedScoreAdmin(CustomModelView, model=FlowFeedScore):
    icon = "fa-solid fa-star"

    column_list = (
        FlowFeedScore.id,
        FlowFeedScore.group_type,
        FlowFeedScore.group_key,
        FlowFeedScore.flow,
        FlowFeedScore.score,
        FlowFeedScore.created_at,
    )

    form_columns = (
        FlowFeedScore.group_type,
        FlowFeedScore.group_key,
        FlowFeedScore.flow,
        FlowFeedScore.score,
    )


class FlowFeedScoreGroupTypeAdmin(CustomModelView, model=FlowFeedScoreGroupType):
    icon = "fa-solid fa-star"

    column_list = (
        FlowFeedScoreGroupType.id,
        FlowFeedScoreGroupType.group_type,
        FlowFeedScoreGroupType.created_at,
        FlowFeedScoreGroupType.enabled,
        FlowFeedScoreGroupType.weight,
    )

    form_columns = (
        FlowFeedScoreGroupType.group_type,
        FlowFeedScoreGroupType.enabled,
        FlowFeedScoreGroupType.weight,
    )
