import csv
import logging
import os
import re

import shared.openai_utils as openai_utils
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from quiz.models import Question
from quiz.quiz_service import SUBJECTS

logger = logging.getLogger(__name__)

"""
This command imports questions from a CSV file into the database.
No embeddings are computed since they should be categorized first.
"""


def clean_text(text: str):
    # Replace sequences of three or more newlines with two newlines
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    # Replace sequences of two ou more spaces with one space
    text = re.sub(r" {2,}", " ", text)
    return text


class Command(BaseCommand):
    help = "Import questions from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="The path to the CSV file")
        parser.add_argument(
            "image_base_path",
            type=str,
            help="The base path to the image directory",
            nargs="?",
            default="",
        )

    def handle(self, *args, **kwargs):
        csv_file_path = kwargs["csv_file"]
        image_base_path = kwargs.get("image_base_path", "")

        with open(csv_file_path, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            rows = [row for row in reader]
            logger.debug(f"Found {len(rows)} questions in the CSV file")

            for row in rows:
                # Validate correct_answer format
                correct_choice_letter = row.get("correct_answer", "").strip()
                if not correct_choice_letter or correct_choice_letter not in [
                    "A",
                    "B",
                    "C",
                    "D",
                    "E",
                ]:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Invalid correct_answer format: {correct_choice_letter}. Skipping question..."
                        )
                    )
                    continue

                # Clean the question text
                question_text = clean_text(row["text"])

                # Validate subject
                subject = row.get("subject", "").strip()
                if subject not in set(SUBJECTS):
                    self.stdout.write(
                        self.style.WARNING(
                            f"Subject {subject} is not valid for question. Skipping question..."
                        )
                    )
                    continue

                # Validate difficulty
                difficulty = row.get("difficulty", "").strip()
                if difficulty not in ["Fácil", "Média", "Difícil", ""]:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Difficulty {difficulty} is not valid for question. Skipping question..."
                        )
                    )
                    continue

                # Process source field - handle USP/FUVEST format
                source = row.get("source", "").strip()
                if source.startswith("USP/FUVEST"):
                    # Extract the year and reformat
                    year_match = re.search(r"\d{4}", source)
                    if year_match:
                        source = f"FUVEST {year_match.group(0)}"

                # Prepare the image path
                image_path = row.get("image_path", "").strip()
                image_file = None

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
                    subject=subject,
                    difficulty=difficulty,
                    source=source,
                    caderno=row.get("caderno", "").strip(),
                )

                # Attach the image to the question if available
                if image_file:
                    question.image.save(image_file.name, image_file)

                # Save the question object
                question.save()
                self.stdout.write(self.style.SUCCESS("Question created successfully"))

                # Create and save the choices
                available_choices = ["A", "B", "C", "D", "E"]
                # Determine if we have 4 or 5 choices
                if "E" not in row or not row["E"].strip():
                    available_choices = ["A", "B", "C", "D"]

                for choice_letter in available_choices:
                    choice_text_or_image = row.get(choice_letter, "").strip()
                    if not choice_text_or_image:
                        continue

                    # Check if the choice is a path to an image (indicating it's an image choice)
                    if choice_text_or_image.endswith((".png", ".jpg", ".jpeg", ".gif")):
                        # Load the image from the base path
                        image_choice_file = None
                        full_image_choice_path = os.path.join(
                            image_base_path, choice_text_or_image
                        )
                        if os.path.exists(full_image_choice_path):
                            with open(full_image_choice_path, "rb") as img_file:
                                image_choice_file = ContentFile(
                                    img_file.read(),
                                    name=os.path.basename(full_image_choice_path),
                                )
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"Choice image {full_image_choice_path} does not exist. Skipping image..."
                                )
                            )

                        # If image exists, save the image as the choice
                        if image_choice_file:
                            is_correct = correct_choice_letter == choice_letter
                            question.choices.create(
                                image=image_choice_file, is_correct=is_correct
                            )

                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Image choice '{choice_letter}' created successfully"
                                )
                            )
                    else:
                        # Handle text choice
                        is_correct = correct_choice_letter == choice_letter
                        question.choices.create(
                            text=choice_text_or_image, is_correct=is_correct
                        )

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Choice '{choice_letter}' created successfully"
                            )
                        )

        self.stdout.write(self.style.SUCCESS("Import completed"))
