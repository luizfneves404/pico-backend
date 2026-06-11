import logging
import os
import re

import pandas as pd
import shared.openai_utils as openai_utils
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from quiz.models import Question

logger = logging.getLogger(__name__)


def clean_text(text):
    if isinstance(text, float):
        # Se o valor for float (provavelmente NaN ou um número), retorna uma string vazia
        return ""
    # Continue o processo de limpeza se o valor for uma string
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    text = re.sub(r" {2,}", " ", text)
    return text


class Command(BaseCommand):
    help = "Import questions from an XLSX file for discursivas"

    def add_arguments(self, parser):
        parser.add_argument("xlsx_file", type=str, help="The path to the XLSX file")
        parser.add_argument(
            "image_base_path",
            type=str,
            help="The base path to the image directory",
            nargs="?",
            default="",
        )

    def handle(self, *args, **kwargs):
        xlsx_file_path = kwargs["xlsx_file"]
        image_base_path = kwargs.get("image_base_path", "")

        # Load the Excel file using pandas
        try:
            df = pd.read_excel(xlsx_file_path)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading XLSX file: {e}"))
            return

        rows = df.to_dict(orient="records")
        logger.debug(f"Found {len(rows)} questions in the XLSX file")

        # Prepare the text for embeddings (text_referencia + text_enunciado)
        questions_texts = [
            "\n\n".join(
                filter(
                    None,
                    [
                        clean_text(row.get("TEXTO_REFERENCIA", "")),
                        clean_text(row.get("TEXTO_ENUNCIADO", "")),
                    ],
                )
            )
            for row in rows
        ]

        # Generate embeddings for all questions
        embeddings = openai_utils.compute_embedding(questions_texts)

        for row, embedding in zip(rows, embeddings):
            # Generate the caderno field
            caderno = f"{row['ARQUIVO_ORIGINAL']}{row['NUM_QUESTAO']}"

            # Clean the text fields
            question_text = "\n\n".join(
                filter(
                    None,
                    [
                        clean_text(row.get("TEXTO_REFERENCIA", "")),
                        clean_text(row.get("TEXTO_ENUNCIADO", "")),
                    ],
                )
            )

            # Prepare the path for the enunciado image if it exists
            image_path = row.get("PATH_REFERENCIA", "") or row.get("PATH_ENUNCIADO", "")
            image_file = None

            # Verifica se o caminho da imagem é válido e converte para string, se necessário
            if isinstance(image_path, float) or not image_path:
                image_path = ""  # Trata valores inválidos como NaN ou números

            if image_path and image_base_path:
                full_image_path = os.path.join(image_base_path, image_path)
                if os.path.exists(full_image_path):
                    with open(full_image_path, "rb") as img_file:
                        image_file = ContentFile(
                            img_file.read(), name=os.path.basename(full_image_path)
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Image {full_image_path} does not exist for question. Skipping image..."
                        )
                    )

            # Create the question object
            question = Question(
                text=question_text,
                subject=row.get("MATERIA", "").strip(),
                source=f"PUC-Rio {str(row['ANO']).strip()}",
                caderno=caderno,
                embedding=embedding,
            )

            # Attach the image to the question if available
            if image_file:
                question.image.save(image_file.name, image_file)
                question.is_active = False  # Deactivate the question for manual review if it has an image

            # Handle the answer text or image for discursiva
            answer_text = clean_text(str(row.get("TEXTO_GABARITO", "")))
            answer_image_path = str(row.get("PATH_GABARITO", ""))
            if answer_text:
                question.answer_text = answer_text
            if answer_image_path and image_base_path:
                full_answer_image_path = os.path.join(
                    image_base_path, answer_image_path
                )
                if os.path.exists(full_answer_image_path):
                    with open(full_answer_image_path, "rb") as img_file:
                        answer_image_file = ContentFile(
                            img_file.read(),
                            name=os.path.basename(full_answer_image_path),
                        )
                        question.answer_image.save(
                            answer_image_file.name, answer_image_file
                        )

            # Save the question object
            question.save()
            self.stdout.write(
                self.style.SUCCESS("Discursive Question created successfully")
            )

        self.stdout.write(self.style.SUCCESS("Import completed"))
