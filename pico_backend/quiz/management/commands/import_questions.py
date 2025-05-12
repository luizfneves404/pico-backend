import asyncio
import csv
import logging
import os
import re

import quiz.utils as quiz_utils
import shared.openai_utils as openai_utils
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from quiz.models import Question

logger = logging.getLogger(__name__)

area_to_range_map_2016_and_before = {
    "Ciências Humanas": (1, 45),
    "Ciências da Natureza": (46, 90),
    "Linguagens": (91, 135),
    "Matemática": (136, 180),
}

area_to_range_map_2017_and_after = {
    "Linguagens": (1, 45),
    "Ciências Humanas": (46, 90),
    "Ciências da Natureza": (91, 135),
    "Matemática": (136, 180),
}


def get_area_from_number(number: int, mapping: dict):
    for area, (start, end) in mapping.items():
        if start <= number <= end:
            return area
    return None


async def find_subject(area: str, rows):
    questions = [
        {
            "question": row["question"],
            "context": row["context"],
            "choices": [row[letter] for letter in ["A", "B", "C", "D", "E"]],
        }
        for row in rows
    ]
    return await quiz_utils.classify_subject_for_questions(area, questions)


def clean_text(text: str):
    # Replace sequences of three or more newlines with two newlines
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    # Replace sequences of two or more spaces with one space
    text = re.sub(r" {2,}", " ", text)
    return text


class Command(BaseCommand):
    help = "Import questions from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="The path to the CSV file")
        parser.add_argument(
            "image_base_path", type=str, help="The base path to the image directory"
        )
        parser.add_argument(
            "area", type=str, help="The area of the questions (e.g. 'Ciências Humanas')"
        )
        parser.add_argument(
            "source", type=str, help="The exam or other source of the questions"
        )
        parser.add_argument(
            "caderno", type=str, help="The caderno of the questions, in the exam"
        )

    def handle(self, *args, **kwargs):
        csv_file_path = kwargs["csv_file"]
        image_base_path = kwargs["image_base_path"]
        area = kwargs["area"]
        source = kwargs["source"]
        caderno = kwargs["caderno"]

        with open(csv_file_path, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            rows = [row for row in reader]
            logger.debug(f"Found {len(rows)} questions in the CSV file")

            if int(source.split(" ")[1]) <= 2016:
                range_map = area_to_range_map_2016_and_before
            else:
                range_map = area_to_range_map_2017_and_after
            in_range_rows = []
            non_range_rows = []
            for row in rows:
                number = int(row["number"])
                if range_map[area][0] <= number <= range_map[area][1]:
                    in_range_rows.append(row)
                else:
                    non_range_rows.append(row)
            logger.debug(
                f"Found {len(in_range_rows)} questions in the range for {area}"
            )
            if non_range_rows:
                logger.debug(
                    f"Found {len(non_range_rows)} questions out of the range for {area}. "
                    f"Ranges that still need to be searched: "
                    f"{[(row['number'], get_area_from_number(int(row['number']), range_map)) for row in non_range_rows]}"
                )

            valid_rows = []
            for row in in_range_rows:
                images = row.get("context-images", "").split(",")
                if len(images) > 1:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Question '{row.get('number')}' has more than one context image. Skipping..."
                        )
                    )
                    continue
                if any(
                    [
                        row[letter].startswith("enem-data/")
                        for letter in ["A", "B", "C", "D", "E"]
                    ]
                ):
                    self.stdout.write(
                        self.style.ERROR(
                            f"Question '{row.get('number')}' has image alternatives. Skipping..."
                        )
                    )
                    continue
                valid_rows.append(row)

            logger.debug(f"Found {len(valid_rows)} valid questions after image checks")

            # clean
            for row in valid_rows:
                row["context"] = clean_text(row.get("context", ""))
                row["question"] = clean_text(row.get("question", ""))

            embeddings = openai_utils.compute_embedding(
                [
                    "\n".join(
                        [
                            row["context"],
                            row["question"],
                            row["A"],
                            row["B"],
                            row["C"],
                            row["D"],
                            row["E"],
                        ]
                    )
                    for row in valid_rows
                ],
            )

            if area in ["Ciências Humanas", "Ciências da Natureza"]:
                subjects = asyncio.run(find_subject(area, valid_rows))
            elif area == "Linguagens":
                subjects = [
                    (
                        "Português"
                        if (int(row["number"]) >= 6 and int(row["number"]) <= 89)
                        or int(row["number"]) >= 96
                        else "Inglês"
                    )
                    for row in valid_rows
                ]
            elif area == "Matemática":
                subjects = ["Matemática"] * len(valid_rows)

            for row, embedding, subject in zip(valid_rows, embeddings, subjects):
                question_number = row.get("number")
                question_question = row["question"]
                question_context = row["context"]

                question_text = (
                    f"{question_context}\n\n{question_question}"
                    if question_context
                    else question_question
                )

                images = row.get("context-images", "").split(",")
                image_path = images[0] if images else None

                question = Question(
                    text=question_text,
                    subject=subject,
                    source=source,
                    caderno=caderno,
                    caderno_number=question_number,
                    embedding=embedding,
                )

                if image_path:
                    full_image_path = os.path.join(image_base_path, image_path)
                    if os.path.exists(full_image_path):
                        with open(full_image_path, "rb") as img_file:
                            question.image.save(
                                image_path, ContentFile(img_file.read())
                            )
                    else:
                        self.stdout.write(
                            self.style.ERROR(
                                f"Image {full_image_path} does not exist for question '{question_number}'. Skipping..."
                            )
                        )
                        continue

                question.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Question '{question_number}' created successfully"
                    )
                )

                correct_choice = row.get("answer")
                for choice in ["A", "B", "C", "D", "E"]:
                    choice_text = row.get(choice, "").strip()
                    is_correct = correct_choice == choice

                    if choice_text:
                        question.choices.create(text=choice_text, is_correct=is_correct)

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Choice '{choice}' for question '{question_number}' created successfully"
                            )
                        )

        self.stdout.write(self.style.SUCCESS("Import completed"))
