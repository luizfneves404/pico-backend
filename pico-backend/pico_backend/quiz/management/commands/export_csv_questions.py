import csv
import io
import logging
from django.core.management.base import BaseCommand
from quiz.models import Question

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Export active questions without images to a CSV file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            help="Path where the CSV file will be saved",
            default="exported_questions.csv",
        )

    def handle(self, *args, **options):
        output_path = options["output"]

        # Query for active questions without images
        questions = Question.objects.filter(
            is_active=True,
            image="",  # Empty image field
        ).prefetch_related("choices")

        count = questions.count()
        self.stdout.write(f"Found {count} active questions without images to export")

        if count == 0:
            self.stdout.write(self.style.WARNING("No questions to export"))
            return

        # Create CSV file
        with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = [
                "id",
                "text",
                "subject",
                "category",
                "subcategory",
                "source",
                "difficulty",
                "parameter_A",
                "parameter_B",
                "parameter_C",
                "answer_text",
                "correct_answer",
                "A",
                "B",
                "C",
                "D",
                "E",
                "is_discursive",
            ]

            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for question in questions:
                # Prepare row data
                row = {
                    "id": question.id,
                    "text": question.text,
                    "subject": question.subject,
                    "category": question.category,
                    "subcategory": question.subcategory,
                    "source": question.source,
                    "difficulty": question.difficulty,
                    "parameter_A": question.parameter_A,
                    "parameter_B": question.parameter_B,
                    "parameter_C": question.parameter_C,
                    "answer_text": question.answer_text,
                    "correct_answer": "",
                    "A": "",
                    "B": "",
                    "C": "",
                    "D": "",
                    "E": "",
                    "is_discursive": False,
                }

                # Add choices if they exist
                choices = list(question.choices.all())

                # Skip questions with image choices
                has_image_choice = any(choice.image for choice in choices)
                if has_image_choice:
                    continue

                if choices:
                    # Multiple choice question
                    for choice in choices:
                        choice_letter = None
                        for letter in ["A", "B", "C", "D", "E"]:
                            if not row[
                                letter
                            ]:  # If this letter position is not filled yet
                                choice_letter = letter
                                break

                        if choice_letter:
                            row[choice_letter] = choice.text
                            if choice.is_correct:
                                row["correct_answer"] = choice_letter
                else:
                    # Discursive question
                    row["is_discursive"] = True

                writer.writerow(row)

        self.stdout.write(
            self.style.SUCCESS(f"Successfully exported questions to {output_path}")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"To download the file to your computer, use: scp user@server:{output_path} /local/path/"
            )
        )
