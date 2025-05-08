from django.core.management.base import BaseCommand
from quiz.models import Question, Challenge, QuestionSelectionMethod
from django.db.models import Q
import random
from tqdm import tqdm
from django.utils import timezone
from datetime import timedelta, datetime
from quiz.utils import CATEGORIES, SUBCATEGORIES
from quiz.session_service import add_questions_to_session
import logging

logger = logging.getLogger(__name__)

PREFERRED_SOURCES = ["FUVEST", "UERJ", "PUC-Rio", "FGV", "UNICAMP", "ENEM", "ENEM PPL"]


class Command(BaseCommand):
    help = "Generate challenges for each subcategory in the system"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("Starting challenge generation by subcategory")
        )

        # Flatten the subcategories dictionary to get all subcategories
        all_subcategories = []
        for subcategory_list in SUBCATEGORIES.values():
            all_subcategories.extend(subcategory_list)

        # Remove duplicates
        all_subcategories = list(set(all_subcategories))

        # Set time parameters
        start_time = timezone.now()
        naive_dt = datetime(2026, 1, 1)
        end_time = timezone.make_aware(naive_dt, timezone.get_current_timezone())

        for subcategory in tqdm(all_subcategories, desc="Generating challenges"):
            # Get questions for this subcategory
            questions = self._get_questions_for_subcategory(subcategory)

            if questions:
                challenge = self._create_challenge(
                    subcategory, questions, start_time, end_time
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created challenge for {subcategory} with {len(questions)} questions. Challenge code: {challenge.code}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"Not enough questions found for {subcategory}")
                )

    def _get_questions_for_subcategory(self, subcategory):
        """Get questions for a specific subcategory, prioritizing preferred sources"""
        # First get preferred source questions
        preferred_query = Q(subcategory__iexact=subcategory)
        source_query = Q()
        for source in PREFERRED_SOURCES:
            source_query |= Q(source__icontains=source)
        preferred_query &= source_query

        preferred_questions = list(Question.objects.filter(preferred_query))

        # Get questions from other sources
        other_query = Q(subcategory__iexact=subcategory) & ~source_query
        other_questions = list(Question.objects.filter(other_query))

        # If we have fewer than 20 questions total, don't create a challenge
        if len(preferred_questions) + len(other_questions) < 20:
            logger.warning(
                f"Only {len(preferred_questions) + len(other_questions)} questions available for {subcategory}, which is less than the minimum 20. Skipping challenge creation."
            )
            return []
        else:
            # If we have fewer than 20 preferred questions, add other questions to reach at least 20
            if len(preferred_questions) < 20:
                needed_other = min(20 - len(preferred_questions), len(other_questions))
                selected_other = random.sample(other_questions, needed_other)
                all_questions = preferred_questions + selected_other
            else:
                # Use all preferred questions
                all_questions = preferred_questions

        return all_questions

    def _create_challenge(self, subcategory, questions, start_time, end_time):
        """Create a challenge with the given subcategory and questions"""
        # Find the category for this subcategory
        category = None
        for cat, subcats in CATEGORIES.items():
            if subcategory in subcats:
                category = cat
                break

        # If category not found in CATEGORIES, check SUBCATEGORIES
        if not category:
            for subcat, subsubcats in SUBCATEGORIES.items():
                if subcategory in subsubcats:
                    # Now find which category contains this subcategory
                    for cat, subcats in CATEGORIES.items():
                        if subcat in subcats:
                            category = cat
                            break
                    if category:
                        break

        title = f"{subcategory} - Desafio Oficial"

        # Create the challenge
        challenge = Challenge.objects.create(
            created_by_id=2,  # pico user ID
            start_time=start_time,
            end_time=end_time,
            selection_method=QuestionSelectionMethod.QUERY_OFFICIAL,
            is_fast=False,
            title=title,
        )

        # Add questions to the challenge using session_service
        add_questions_to_session(challenge.id, questions)

        return challenge
