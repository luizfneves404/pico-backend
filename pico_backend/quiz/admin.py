import csv
import datetime
import io
import logging
import re

import numpy as np
import shared.openai_utils as openai_utils
from celery.result import AsyncResult
from django.contrib import admin, messages
from django.core.files.storage import default_storage
from django.db.models import Count, F, Sum, Value
from django.db.models.functions import Coalesce, Length
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.safestring import mark_safe
from import_export import resources
from import_export.admin import ImportExportMixin

import quiz.tasks as quiz_tasks
from quiz import session_pdf
from quiz.forms import (
    CSVUploadForm,
    CSVUploadFormNumber,
    DiscursiveQuestionsCSVUploadForm,
    ImageUploadForm,
    StudentQuestionsCSVUploadForm,
)
from quiz.models import (
    Challenge,
    Choice,
    Duel,
    Question,
    Quiz,
    Round,
    SessionParticipation,
    SessionQuestion,
    SessionQuestionUser,
    Turn,
    UserInfo,
)
from quiz.utils import (
    categorize_question,
    classify_difficulty,
    encode_image,
    find_errors,
    generate_answer,
    generate_questions_from_images,
    rerun_embeddings,
    validate_category_and_subcategory,
)

logger = logging.getLogger(__name__)


class QuestionResource(resources.ModelResource):
    is_embedded = resources.Field(readonly=True)

    class Meta:
        use_bulk = True
        model = Question
        fields = (
            "id",
            "text",
            "answer_text",
            "source",
            "area",
            "caderno",
            "caderno_number",
            "subject",
            "is_active",
            "created_at",
            "difficulty",
            "is_embedded",
            "category",
            "subcategory",
            "parameter_A",
            "parameter_B",
            "parameter_C",
        )

    def dehydrate_is_embedded(self, question):
        return question.embedding is not None and question.embedding.any()


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 5


class HasChoiceFilter(admin.SimpleListFilter):
    title = "is multiple choice"
    parameter_name = "has_related"

    def lookups(self, request, model_admin) -> tuple[tuple[str, str], tuple[str, str]]:
        return (
            ("yes", "Yes"),
            ("no", "No"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.annotate(num_related=Count("choices")).filter(
                num_related__gt=0
            )
        if self.value() == "no":
            return queryset.annotate(num_related=Count("choices")).filter(num_related=0)


class AreaFilter(admin.SimpleListFilter):
    title = "area"
    parameter_name = "area"

    def lookups(
        self, request, model_admin
    ) -> tuple[tuple[str, str], tuple[str, str], tuple[str, str], tuple[str, str]]:
        return (
            ("Ciências Humanas", "Ciências Humanas"),
            ("Ciências da Natureza", "Ciências da Natureza"),
            ("Linguagens", "Linguagens"),
            ("Matemática", "Matemática"),
        )

    def queryset(self, request, queryset):
        if self.value():
            filtered_ids = [obj.id for obj in queryset if obj.area == self.value()]
            return queryset.filter(id__in=filtered_ids)
        return queryset


class DateListFilter(admin.SimpleListFilter):
    title = "date"
    parameter_name = "timestamp"

    def lookups(self, request, model_admin):
        dates: set[datetime.date] = set(
            [obj.timestamp.date() for obj in model_admin.model.objects.all()]
        )
        return [(date, date) for date in dates]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(timestamp__date=self.value())
        return queryset


@admin.register(UserInfo)
class UserInfoAdmin(admin.ModelAdmin):
    ordering = ["id"]
    search_fields = ["user__username"]
    fields = [
        "user",
        "math_score",
        "language_score",
        "humanities_score",
        "science_score",
        "average_score",
        "dynamic_score",
    ]
    readonly_fields = ["average_score"]
    list_display = [
        "user",
        "math_score",
        "language_score",
        "humanities_score",
        "science_score",
        "average_score",
        "dynamic_score",
    ]
    raw_id_fields = ["user"]
    actions = ["update_score", "reset_dynamic_scores"]

    def update_score(self, request, queryset):
        for user_info in queryset:
            quiz_tasks.task_update_score.delay(user_info.user_id)

    def reset_dynamic_scores(self, request, queryset):
        quiz_tasks.task_reset_dynamic_scores.delay()


@admin.register(Question)
class QuestionAdmin(ImportExportMixin, admin.ModelAdmin):
    change_list_template = "admin/quiz/question/change_list.html"
    resource_class = QuestionResource
    ordering = ["id"]
    search_fields = ["id", "text", "answer_text", "source"]
    fields = (
        "is_active",
        "allow_resubmit",
        "image",
        "video_url",
        "extra_embedding_text",
        "text",
        "answer_text",
        "answer_image",
        "source",
        "subject",
        "created_at",
        "difficulty",
        "embedding",
        "caderno",
        "caderno_number",
        "category",
        "subcategory",
        "parameter_A",
        "parameter_B",
        "parameter_C",
        "is_fast",
    )
    readonly_fields = ["created_at"]
    list_display = [
        "id",
        "source",
        "caderno",
        "caderno_number",
        "subject",
        "is_active",
        "created_at",
        "difficulty",
        "text",
        "category",
        "subcategory",
        "parameter_A",
        "parameter_B",
        "parameter_C",
        "is_fast",
    ]
    inlines = [ChoiceInline]
    list_filter = (
        HasChoiceFilter,
        "is_active",
        AreaFilter,
        "source",
        "subject",
        "allow_resubmit",
    )
    actions = [
        "find_category_and_subcategory",
        "delete_caderno_number",
        "validate_categorization",
        "turn_active",
        "turn_inactive",
        "generate_answers",
        "import_student_questions",
        "classify_fast_questions",
        "reclassify_difficulty_ENEM",
        "classify_difficulty",
        "rerun_embeddings",
        "find_errors",
    ]

    def reclassify_difficulty_ENEM(self, request, queryset):
        """
        Para cada área (propriedade `area`), classifica:
         - 35% com menor valor de parameter_B como "Fácil",
         - 20% com maior valor de parameter_B como "Difícil",
         - O restante como "Média".
        Apenas questões com valor definido em parameter_B são consideradas.
        """
        # Filtra apenas as questões que possuem valor em parameter_B
        qs = queryset.exclude(parameter_B__isnull=True)

        # Agrupa as questões por área. Se a área for None, pode-se agrupar como "Sem Área" (opcional)
        grouped = {}
        for question in qs:
            area = question.area
            if not area:
                continue
            grouped.setdefault(area, []).append(question)

        updated_questions = []
        for area, questions in grouped.items():
            # Ordena as questões pelo valor de parameter_B (do menor para o maior)
            questions.sort(key=lambda q: q.parameter_B)
            n = len(questions)
            if n == 0:
                continue

            # Calcula a quantidade para as categorias
            easy_count = int(n * 0.35)
            hard_count = int(n * 0.20)

            # Itera sobre as questões classificando-as
            for index, question in enumerate(questions):
                if index < easy_count:
                    question.difficulty = "Fácil"
                elif index >= n - hard_count:
                    question.difficulty = "Difícil"
                else:
                    question.difficulty = "Média"
                updated_questions.append(question)

        # Atualiza em massa os registros alterados
        Question.objects.bulk_update(updated_questions, ["difficulty"])

        self.message_user(
            request,
            f"Atualizadas {len(updated_questions)} questões com base em parameter_B.",
            messages.SUCCESS,
        )

    def classify_fast_questions(self, request, queryset):
        def mark_fast_questions(qs, description=""):
            if not qs.exists():
                return f"{description}: No questions to process\n"

            # Anota o tamanho de "text", "extra_embedding_text" e soma o tamanho dos textos das alternativas
            questions = qs.annotate(
                text_length=Length(Coalesce("text", Value(""))),
                extra_length=Length(Coalesce("extra_embedding_text", Value(""))),
                choices_length=Coalesce(
                    Sum(Length(Coalesce("choices__text", Value("")))), Value(0)
                ),
            ).annotate(
                total_length=F("text_length") + F("extra_length") + F("choices_length")
            )

            total_count = questions.count()
            threshold_index = int(total_count * 0.2)

            if threshold_index > 0:
                # Get the threshold length without ordering
                threshold_length = questions.order_by("total_length").values_list(
                    "total_length", flat=True
                )[threshold_index - 1]

                # Get the IDs of questions to mark as fast (without ordering)
                fast_question_ids = questions.filter(
                    total_length__lte=threshold_length
                ).values_list("id", flat=True)

                # Update questions using the IDs
                qs.filter(id__in=fast_question_ids).update(is_fast=True)
                fast_count = len(fast_question_ids)

                return f"{description}: {fast_count} questions marked as fast (length <= {threshold_length})\n"
            return f"{description}: No questions marked as fast (too few questions)\n"

        # Inicia definindo as perguntas selecionadas como não fast
        queryset.update(is_fast=False)
        active_questions = queryset.filter(is_active=True)

        results = []

        # Processa as perguntas de Matemática por subcategoria
        math_subcategories = (
            active_questions.filter(subject="Matemática")
            .values_list("subcategory", flat=True)
            .distinct()
        )

        if math_subcategories.exists():
            for subcategory in math_subcategories:
                if subcategory:  # Ignora subcategorias vazias
                    math_qs = active_questions.filter(
                        subject="Matemática", subcategory=subcategory
                    )
                result = mark_fast_questions(math_qs, f"Math - {subcategory}")
                results.append(result)

        # Processa todas as demais perguntas (não Matemática) juntas
        non_math_qs = active_questions.exclude(subject="Matemática")
        if non_math_qs.exists():
            result = mark_fast_questions(non_math_qs, "Non-math questions")
            results.append(result)

        # Exibe os resultados
        self.message_user(
            request,
            f"Classification complete for {active_questions.count()} selected questions:\n"
            + "\n".join(results),
        )

        logger.info(
            f"Classification complete for {active_questions.count()} selected questions:\n"
            + "\n".join(results)
        )

    classify_fast_questions.short_description = (
        "Classify fast questions (shortest 20%%)"
    )

    def clean_text(self, text: str):
        # Replace sequences of three or more newlines with two newlines
        text = re.sub(r"\n{3,}", "\n\n", text.strip())
        # Replace sequences of two ou more spaces with one space
        text = re.sub(r" {2,}", " ", text)
        return text

    def import_student_questions(self, request):
        if request.method == "POST":
            form = StudentQuestionsCSVUploadForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]
                try:
                    decoded_file = csv_file.read().decode("utf-8")
                    reader = csv.DictReader(io.StringIO(decoded_file))
                    rows = list(reader)

                    # Prepare texts for embeddings
                    questions_texts = [
                        "\n".join(
                            [
                                self.clean_text(row["text"]),
                                self.clean_text(row["A"]),
                                self.clean_text(row["B"]),
                                self.clean_text(row["C"]),
                                self.clean_text(row["D"]),
                            ]
                        )
                        for row in rows
                    ]

                    # Generate embeddings
                    embeddings = openai_utils.compute_embedding(questions_texts)

                    for row, embedding in zip(rows, embeddings):
                        question_text = self.clean_text(row["text"])
                        answer_text = self.clean_text(row["answer_text"])

                        # Create question
                        question = Question(
                            text=question_text,
                            source="Litoral Sul",
                            embedding=embedding,
                            is_active=False,
                            answer_text=answer_text,
                        )
                        question.save()

                        # Create choices
                        correct_choice_letter = row["correct_answer"].strip()
                        for choice_letter in ["A", "B", "C", "D"]:
                            choice_text = row.get(choice_letter, "").strip()
                            if choice_text:
                                is_correct = correct_choice_letter == choice_letter
                                question.choices.create(
                                    text=choice_text, is_correct=is_correct
                                )

                    self.message_user(
                        request, f"Successfully imported {len(rows)} questions"
                    )
                    return HttpResponseRedirect("../")
                except Exception as e:
                    self.message_user(
                        request,
                        f"Error importing questions: {str(e)}",
                        level=messages.ERROR,
                    )
                    return HttpResponseRedirect("../")
        else:
            form = StudentQuestionsCSVUploadForm()

        return render(request, "admin/import_student_questions.html", {"form": form})

    def import_discursive_questions(self, request):
        if request.method == "POST":
            form = DiscursiveQuestionsCSVUploadForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]
                try:
                    decoded_file = csv_file.read().decode("utf-8")
                    reader = csv.DictReader(io.StringIO(decoded_file))
                    rows = list(reader)

                    # Prepare texts for embeddings
                    questions_texts = [
                        "\n".join(
                            [
                                self.clean_text(row["text"]),
                                self.clean_text(row["answer_text"]),
                            ]
                        )
                        for row in rows
                    ]

                    # Generate embeddings
                    embeddings = openai_utils.compute_embedding(questions_texts)

                    for row, embedding in zip(rows, embeddings):
                        question_text = self.clean_text(row["text"])
                        answer_text = self.clean_text(row["answer_text"])
                        subject = row.get("subject", "").strip()
                        source = row.get("source", "").strip()

                        # Create question
                        question = Question(
                            text=question_text,
                            answer_text=answer_text,
                            subject=subject,
                            source=source,
                            embedding=embedding,
                            is_active=False,
                        )
                        question.save()

                    self.message_user(
                        request, f"Successfully imported {len(rows)} questions"
                    )
                    return HttpResponseRedirect("../")
                except Exception as e:
                    self.message_user(
                        request,
                        f"Error importing questions: {str(e)}",
                        level=messages.ERROR,
                    )
                    return HttpResponseRedirect("../")
        else:
            form = DiscursiveQuestionsCSVUploadForm()

        return render(request, "admin/import_discursive_questions.html", {"form": form})

    def turn_active(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(
            request,
            "Questões ativadas com sucesso",
        )

    def turn_inactive(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(
            request,
            "Questões desativadas com sucesso",
        )

    def validate_categorization(self, request, queryset):
        for question in queryset:
            try:
                # Verifica se a questão é de múltipla escolha
                if not question.choices.exists():
                    logger.warning(
                        f"Questão {question.id} não é de múltipla escolha. Ignorando."
                    )
                    continue

                # Chama a função de validação passando o ID da questão
                # Chama a função de validação de forma assíncrona
                result = validate_category_and_subcategory.delay(question.id)

                # Aqui, você só pode registrar o ID da tarefa, não o resultado imediato
                logger.info(
                    f"Tarefa Celery iniciada para a questão {question.id}, tarefa ID: {result.id}"
                )

            except Exception as e:
                logger.error(
                    f"Erro ao validar categorização para questão {question.id}: {e}"
                )
                self.message_user(
                    request,
                    f"Erro ao validar categorização para questão {question.id}: {e}",
                    level=messages.ERROR,
                )
                continue

        self.message_user(
            request,
            f"Validação iniciada para {queryset.count()} questões.",
            level=messages.SUCCESS,
        )

    def upload_images_for_question_generation(self, request):
        if request.method == "POST":
            form = ImageUploadForm(request.POST, request.FILES)
            if form.is_valid():
                images = form.cleaned_data[
                    "images"
                ]  # Now this will return a list of files
                source = form.cleaned_data["source"]
                questions_per_image = form.cleaned_data["questions_per_image"]
                subject = form.cleaned_data["subject"]
                extra_instructions = form.cleaned_data["extra_instructions"]

                if subject not in set(
                    [
                        "Matemática",
                        "Português",
                        "Biologia",
                        "Física",
                        "Química",
                        "História",
                        "Geografia",
                        "Sociologia",
                        "Filosofia",
                    ]
                ):
                    messages.error(request, "Invalid subject.")
                    return HttpResponseRedirect(request.get_full_path())

                if not images:
                    messages.error(request, "Please upload at least one image.")
                    return HttpResponseRedirect(request.get_full_path())

                # Convert images to base64 usando a função encode_image
                base64_images = []
                for image in images:
                    try:
                        encoded_image = encode_image(image)
                        base64_images.append(f"data:image/jpeg;base64,{encoded_image}")
                    except Exception as e:
                        logger.error(f"Erro ao codificar a imagem {image.name}: {e}")
                        messages.error(
                            request, f"Erro ao processar a imagem {image.name}."
                        )
                        return HttpResponseRedirect(request.get_full_path())

                # Pass base64 images to Celery task
                try:
                    result = generate_questions_from_images.delay(
                        base64_images,
                        source,
                        subject,
                        extra_instructions,
                        questions_per_image,
                    )
                    messages.success(
                        request,
                        f"Perguntas estão sendo geradas. ID da Tarefa: {result.id}",
                    )
                    return HttpResponseRedirect(request.get_full_path())
                except Exception as e:
                    logger.error(f"Erro ao iniciar a tarefa Celery: {e}")
                    messages.error(request, "Erro ao iniciar a geração das perguntas.")
                    return HttpResponseRedirect(request.get_full_path())
            else:
                messages.error(request, "Submissão de formulário inválida.")
        else:
            form = ImageUploadForm()

        return render(request, "admin/upload_images.html", {"form": form})

    def upload_csv(self, request):
        if request.method == "POST":
            logger.info("Iniciando o upload do CSV para parametrização.")
            form = CSVUploadForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]
                source = form.cleaned_data["source"]
                prova_codes_input = form.cleaned_data["prova_codes"]
                prova_codes = [
                    code.strip() for code in prova_codes_input.split(",")
                ]  # Lista de códigos de prova
                logger.info(f"Source: {source}, Prova Codes: {prova_codes}")

                try:
                    decoded_file = csv_file.read().decode("ISO-8859-1")
                    io_string = io.StringIO(decoded_file)
                    reader = (
                        list(csv.DictReader(io_string, delimiter=";"))
                        if source != "ENEM 2017"
                        else list(csv.DictReader(io_string, delimiter=","))
                    )
                    logger.info(f"Arquivo CSV lido com sucesso. Linhas: {len(reader)}")
                except Exception as e:
                    logger.error(f"Erro ao ler e decodificar o arquivo CSV: {e}")
                    messages.error(request, "Erro ao processar o arquivo CSV.")
                    return HttpResponseRedirect(request.get_full_path())

                param_b_values = []
                years_before = [
                    "ENEM 2010",
                    "ENEM 2011",
                    "ENEM 2012",
                    "ENEM 2013",
                    "ENEM 2014",
                    "ENEM 2015",
                ]
                years_after = [
                    "ENEM 2016",
                    "ENEM 2017",
                    "ENEM 2018",
                    "ENEM 2019",
                    "ENEM 2020",
                    "ENEM 2021",
                    "ENEM 2022",
                    "ENEM 2023",
                ]

                for row in reader:
                    if (
                        (row["TX_COR"]).upper() != "AMARELA"
                        and (row["TX_COR"]).upper() != "AMARELO"
                    ) or row["CO_PROVA"] not in prova_codes:
                        continue
                    try:
                        co_posicao = int(row["CO_POSICAO"])
                        if co_posicao <= 5:
                            continue
                        value = float(row["NU_PARAM_B"])
                        param_b_values.append(value)
                    except ValueError:
                        logger.warning(f"Valor inválido em NU_PARAM_B na linha: {row}")
                        continue

                if not param_b_values:
                    logger.error(
                        "Nenhuma questão válida encontrada para os códigos de prova fornecidos."
                    )
                    messages.error(
                        request,
                        "No valid 'AMARELA' colored questions with valid NU_PARAM_B found in the CSV for the provided prova codes.",
                    )
                    return HttpResponseRedirect(request.get_full_path())

                mean_b = np.mean(param_b_values)
                std_b = np.std(param_b_values)
                logger.info(f"Média de NU_PARAM_B: {mean_b}, Desvio padrão: {std_b}")

                def categorize_difficulty(value, mean, std):
                    if value < (mean - 0.55 * std):
                        return "Fácil"
                    elif value > (mean + 0.55 * std):
                        return "Difícil"
                    else:
                        return "Média"

                for row in reader:
                    if (
                        (row["TX_COR"]).upper() != "AMARELA"
                        and (row["TX_COR"]).upper() != "AMARELO"
                    ) or row["CO_PROVA"] not in prova_codes:
                        continue

                    try:
                        co_posicao = int(row["CO_POSICAO"])
                        if (source in years_after and co_posicao <= 5) or (
                            source in years_before
                            and (co_posicao >= 91 and co_posicao <= 95)
                        ):
                            continue
                        nu_param_a = float(row["NU_PARAM_A"])
                        nu_param_b = float(row["NU_PARAM_B"])
                        nu_param_c = float(row["NU_PARAM_C"])
                    except ValueError:
                        logger.warning(f"Erro ao processar linha do CSV: {row}")
                        continue

                    difficulty = categorize_difficulty(nu_param_b, mean_b, std_b)
                    logger.info(f"Questão {co_posicao} classificada como {difficulty}.")

                    try:
                        question = Question.objects.get(
                            caderno_number=co_posicao, source=source
                        )
                        question.parameter_A = nu_param_a
                        question.parameter_B = nu_param_b
                        question.parameter_C = nu_param_c
                        question.difficulty = difficulty
                        question.save()
                        logger.info(f"Questão {co_posicao} atualizada com sucesso.")
                    except Question.DoesNotExist:
                        logger.warning(
                            f"Questão com caderno_number {co_posicao} e source {source} não encontrada."
                        )
                        continue

                messages.success(request, "CSV file has been processed successfully")
                logger.info("Processamento do CSV concluído com sucesso.")
                return HttpResponseRedirect(request.get_full_path())

            else:
                logger.warning("Formulário inválido.")
        else:
            form = CSVUploadForm()

        return render(request, "admin/upload_csv.html", {"form": form})

    def upload_csv_number(self, request):
        if request.method == "POST":
            logger.info(
                "Iniciando o upload do CSV para atualização de números de caderno."
            )
            form = CSVUploadFormNumber(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]
                source = form.cleaned_data["source"]
                try:
                    decoded_file = csv_file.read().decode("utf-8")
                    io_string = io.StringIO(decoded_file)
                    reader = list(csv.DictReader(io_string, delimiter=","))
                    logger.info(f"Arquivo CSV lido com sucesso. Linhas: {len(reader)}")

                    matched_questions = (
                        0  # Contador de questões processadas com sucesso
                    )

                    for row in reader:
                        csv_a = (row["A"].strip().lower())[:10]
                        csv_b = (row["B"].strip().lower())[:10]
                        csv_context = row["context"].strip().lower()[:15]
                        caderno_number = int(row["number"])

                        # Filtra as questões com base no source
                        questions = Question.objects.filter(source=source)
                        matching_questions = []

                        for question in questions:
                            choices = list(question.choices.order_by("id"))
                            if len(choices) >= 2:
                                choice_a = choices[0].text.strip().lower()
                                choice_b = choices[1].text.strip().lower()

                                # Verificação inicial: apenas alternativas
                                if choice_a.startswith(csv_a) and choice_b.startswith(
                                    csv_b
                                ):
                                    matching_questions.append(question)

                        # Se mais de uma questão corresponder, usa o contexto como critério de desempate
                        if len(matching_questions) > 1:
                            refined_matches = [
                                q
                                for q in matching_questions
                                if csv_context in q.extra_embedding_text.strip().lower()
                            ]

                            # Log detalhado para desempate
                            for q in matching_questions:
                                logger.info(
                                    f"Desempate: CSV Context: '{csv_context}', "
                                    f"Question Extra Embedding Text: '{q.extra_embedding_text.strip().lower()}'"
                                )

                            # Se o desempate resultar em uma única questão, prossiga
                            if len(refined_matches) == 1:
                                question = refined_matches[0]
                                logger.warning("ambiguidade resolvida!")
                            else:
                                logger.warning(
                                    f"Ambiguidade encontrada para o caderno {caderno_number}: "
                                    f"{len(matching_questions)} questões correspondem aos critérios. "
                                    f"{len(refined_matches)} após o desempate por contexto."
                                )
                                continue
                        elif len(matching_questions) == 1:
                            question = matching_questions[0]
                        else:
                            continue

                        # Associação final
                        question.caderno_number = caderno_number
                        question.caderno = "Amarelo"
                        question.save()
                        matched_questions += 1
                        logger.info(
                            f"Questão {question.id} associada ao caderno {caderno_number}."
                        )

                    messages.success(
                        request,
                        f"CSV file has been processed successfully. Matched questions: {matched_questions}",
                    )
                    logger.info(
                        f"Processamento do CSV concluído com sucesso. Questões associadas: {matched_questions}"
                    )
                    return HttpResponseRedirect(request.get_full_path())

                except Exception as e:
                    logger.error(f"Erro ao processar o CSV: {e}")
                    messages.error(request, f"Erro ao processar o CSV: {e}")
                    return HttpResponseRedirect(request.get_full_path())

            else:
                logger.warning("Formulário inválido.")
        else:
            form = CSVUploadFormNumber()

        return render(request, "admin/upload_csv_number.html", {"form": form})

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        quiz_tasks.task_add_embedding_to_question.delay_on_commit(form.instance.id)

    def rerun_embeddings(self, request, queryset):
        for question in queryset:
            rerun_embeddings.delay(question.id).forget()
        self.message_user(
            request, f"Embeddings sendo reprocessados para {queryset.count()} questões."
        )

    def find_category_and_subcategory(self, request, queryset):
        for question in queryset:
            categorize_question.delay(question.id, 0).forget()
        self.message_user(
            request, f"Categorias sendo processadas para {queryset.count()} questões."
        )

    find_category_and_subcategory.short_description = "Find category using OpenAI"

    def classify_difficulty(self, request, queryset):
        for question in queryset:
            classify_difficulty.delay(question.id).forget()
        self.message_user(
            request, f"Dificuldade sendo processada para {queryset.count()} questões."
        )

    classify_difficulty.short_description = "Classify difficulty using OpenAI"

    def generate_answers(self, request, queryset):
        for question in queryset:
            generate_answer.delay(question.id, 0).forget()
        self.message_user(
            request, f"Respostas sendo geradas para {queryset.count()} questões."
        )

    generate_answers.short_description = "Generate questions answers using OpenAI"

    def find_errors(self, request, queryset):
        for question in queryset:
            find_errors.delay(question.id).forget()
        self.message_user(
            request, f"Erros sendo encontrados para {queryset.count()} questões."
        )

    find_errors.short_description = "Find errors using OpenAI"

    def delete_caderno_number(self, request, queryset):
        # Atualiza todas as questões selecionadas, definindo caderno_number como None
        queryset.update(caderno_number=None)
        self.message_user(
            request,
            f"Número da questão deletado para {queryset.count()} questões.",
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "upload_csv/",
                self.admin_site.admin_view(self.upload_csv),
                name="upload_csv",
            ),
            path(
                "upload_csv_number/",
                self.admin_site.admin_view(self.upload_csv_number),
                name="upload_csv_number",
            ),
            path(
                "upload_images/",
                self.admin_site.admin_view(self.upload_images_for_question_generation),
                name="upload_images",
            ),
            path(
                "import_student_questions/",
                self.admin_site.admin_view(self.import_student_questions),
                name="import_student_questions",
            ),
            path(
                "import_discursive_questions/",
                self.admin_site.admin_view(self.import_discursive_questions),
                name="import_discursive_questions",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["upload_csv_url"] = reverse("admin:upload_csv")
        extra_context["upload_csv_number_url"] = reverse("admin:upload_csv_number")
        extra_context["upload_images_url"] = reverse("admin:upload_images")
        extra_context["import_student_questions_url"] = reverse(
            "admin:import_student_questions"
        )
        extra_context["import_discursive_questions_url"] = reverse(
            "admin:import_discursive_questions"
        )
        return super().changelist_view(request, extra_context=extra_context)

    """ def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "questions-add-csv/",
                self.add_questions_csv,
                name="add_questions_csv",
            ),
        ]
        return custom_urls + urls """

    """ def add_questions_csv(self, request):
        if request.method == "POST":
            form = ExamQuestionCSVUploadForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]
                decoded_file = csv_file.read().decode("utf-8")
                io_string = io.StringIO(decoded_file)
                reader = csv.DictReader(io_string)

                questions = []
                answers = []
                for row in reader:
                    questions.append(row["question"])
                    answers.append(row["answer"])

                create_questions_sync_workflow(questions, answers)

                self.message_user(request, "CSV file has been imported successfully")
                return HttpResponseRedirect("..")
        else:
            form = ExamQuestionCSVUploadForm()

        context = {"form": form}
        return render(request, "admin/csv_form.html", context) """


@admin.register(SessionQuestion)
class SessionQuestionAdmin(admin.ModelAdmin):
    ordering = ["id"]
    search_fields = ["id", "session__query", "question__text"]
    fields = ["session", "question", "order"]
    list_display = ["id", "session", "question", "order"]
    raw_id_fields = ["session", "question"]
    list_filter = ["session__area", "session__source_filter", "session__difficulty"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("session", "question")


@admin.register(SessionQuestionUser)
class SessionQuestionUserAdmin(admin.ModelAdmin):
    ordering = ["id"]
    search_fields = [
        "id",
        "user__username",
        "session_question__session__query",
        "session_question__question__text",
        "submitted_text",
    ]
    fields = [
        "session_question",
        "user",
        "choice",
        "submitted_text",
        "feedback",
        "grade",
        "timestamp",
        "timed_out",
    ]
    readonly_fields = ["timestamp"]
    list_display = [
        "id",
        "choice__is_correct",
        "user",
        "session_question",
        "session_question__session",
        "session_question__question",
        "choice",
        "submitted_text",
        "question_subject",
        "question_category",
        "question_subcategory",
        "feedback",
        "grade",
        "timestamp",
        "timed_out",
    ]
    list_filter = [
        "session_question__session__area",
        DateListFilter,
        "choice__is_correct",
        "timed_out",
    ]
    raw_id_fields = ["session_question", "user", "choice"]
    actions = ["export_answers_async"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "session_question",
                "session_question__session",
                "session_question__question",
                "user",
                "choice",
            )
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "check_export_status/<str:task_id>/",
                self.check_export_status,
                name="check_export_status",
            ),
        ]
        return custom_urls + urls

    def check_export_status(self, request, task_id):
        task = AsyncResult(task_id)
        if task.ready():
            file_path = task.result
            if default_storage.exists(file_path):
                file = default_storage.open(file_path, "rb")
                response = FileResponse(file)
                response["Content-Disposition"] = (
                    f'attachment; filename="{file_path.split("/")[-1]}"'
                )
                return response
            else:
                return HttpResponse("Export file not found.")
        else:
            return HttpResponse("Export is still in progress. Please check back later.")

    def export_answers_async(self, request, queryset):
        task = quiz_tasks.export_answers_celery.delay(
            list(queryset.values_list("id", flat=True))
        )
        check_url = reverse("admin:check_export_status", args=[task.id])
        messages.success(
            request,
            mark_safe(f"Export started. Check status <a href='{check_url}'>here</a>."),
        )

    export_answers_async.short_description = "Export Answers (Async)"


class BaseSessionAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        # Ensure the session_type is only set during object creation or remains unchanged
        if not obj.pk:  # Only set if the object is new
            obj.session_type = obj.__class__.__name__.lower()
        else:
            # Prevent modifying session_type if the object already exists
            obj.session_type = obj._meta.model_name.lower()
        super().save_model(request, obj, form, change)

    def generate_pdf(self, request: HttpRequest, queryset):
        for session in queryset:
            pdf_file = session_pdf.get_session_pdf(session.id)
            response = HttpResponse(pdf_file, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{pdf_file.name}"'
            return response

    generate_pdf.short_description = "Generate PDF for selected Sessions"


@admin.register(Quiz)
class QuizAdmin(BaseSessionAdmin):
    ordering = ["id"]
    search_fields = [
        "id",
        "query",
        "area",
        "code",
        "source_filter",
        "difficulty",
        "created_by__username",
    ]
    fields = [
        "query",
        "title",
        "created_at",
        "area",
        "source_filter",
        "difficulty",
        "question_type",
        "quiz_type",
        "selection_method",
        "selection_source",
        "created_by",
        "parent_session",
        "code",
    ]
    readonly_fields = ["created_at"]
    list_display = [
        "id",
        "created_at",
        "title",
        "query",
        "area",
        "source_filter",
        "difficulty",
        "question_type",
        "quiz_type",
        "selection_method",
        "selection_source",
        "session_type",
        "created_by",
        "parent_session",
        "code",
    ]
    raw_id_fields = ["created_by", "parent_session"]
    actions = ["generate_pdf", "export_session_stats"]


@admin.register(Duel)
class DuelAdmin(BaseSessionAdmin):
    ordering = ["id"]
    search_fields = [
        "id",
        "code",
        "created_by__username",
    ]
    fields = [
        "query",
        "created_at",
        "created_by",
        "parent_session",
        "code",
        "tournament",
        "selection_method",
        "selection_source",
        "n_questions_per_round",
        "is_fast",
        "winner",
        "duel_status",
        "current_turn",
        "current_turn_round",
        "current_turn_user",
        "current_turn_start_time",
        "current_turn_phase",
    ]
    readonly_fields = [
        "created_at",
        "current_turn_round",
        "current_turn_user",
        "current_turn_start_time",
        "current_turn_phase",
    ]
    list_display = [
        "id",
        "created_at",
        "selection_method",
        "selection_source",
        "query",
        "created_by",
        "is_fast",
        "parent_session",
        "tournament",
        "code",
        "winner",
        "duel_status",
        "current_turn",
        "current_turn_user",
        "current_turn_round",
        "current_turn_start_time",
        "current_turn_phase",
    ]
    list_filter = [
        "is_fast",
        "tournament",
        "selection_method",
    ]
    raw_id_fields = [
        "created_by",
        "parent_session",
        "winner",
        "current_turn",
        "tournament",
    ]
    actions = ["generate_pdf"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "current_turn",
            )
        )


@admin.register(Turn)
class TurnAdmin(admin.ModelAdmin):
    ordering = ["id"]
    search_fields = ["id", "user__username"]
    fields = ["user", "round", "start_time", "phase", "_order"]
    list_display = ["id", "user", "round", "start_time", "phase", "_order"]
    raw_id_fields = ["user", "round"]


class TurnInline(admin.TabularInline):
    model = Turn
    extra = 0
    fields = ["user", "start_time", "phase", "_order"]
    readonly_fields = ["_order"]


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    ordering = ["id"]
    search_fields = ["id", "duel__code", "duel__created_by__username"]
    fields = ["duel", "_order"]
    readonly_fields = ["_order"]
    list_display = ["id", "duel", "_order"]
    raw_id_fields = ["duel"]
    inlines = [TurnInline]


@admin.register(Challenge)
class ChallengeAdmin(BaseSessionAdmin):
    search_fields = [
        "id",
        "code",
        "title",
        "created_by__username",
    ]
    fields = [
        "code",
        "title",
        "created_at",
        "created_by",
        "start_time",
        "end_time",
        "selection_method",
        "selection_source",
        "is_fast",
    ]
    readonly_fields = ["created_at"]
    list_display = [
        "id",
        "created_at",
        "code",
        "title",
        "start_time",
        "end_time",
        "selection_method",
        "selection_source",
        "is_fast",
    ]
    actions = ["generate_pdf"]


"""def export_session_stats(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="session_stats.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "Session ID",
                "User username",
                "Total Answers",
                "Correct Answers",
                "Start Time",
                "End Time",
                "Total Time",
            ]
        )

        for quiz in queryset:
            for stat in quiz_service.get_quiz_stats(quiz):
                writer.writerow(
                    [
                        quiz.id,
                        stat["user__username"],
                        stat["total_answers"],
                        stat["correct_answers"],
                        stat["start_time"],
                        stat["end_time"],
                        stat["total_time"],
                    ]
                )

        return response

    export_session_stats.short_description = "Export Quiz Stats for selected Quizzes" """


@admin.register(SessionParticipation)
class SessionParticipationAdmin(admin.ModelAdmin):
    ordering = ["id"]
    search_fields = ["id", "user__username", "session__query"]
    fields = ["user", "session", "confirmed", "duel_score_change"]
    list_display = ["id", "user", "session", "confirmed", "duel_score_change"]
    raw_id_fields = ["user", "session"]
