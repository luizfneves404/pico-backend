import logging

from django.db import migrations, models, transaction
from django.db.models import Prefetch
from django.db.utils import IntegrityError

logger = logging.getLogger(__name__)


def migrate_quiz_to_session(apps, schema_editor):
    BonusEvent = apps.get_model("bonus_events", "BonusEvent")
    Message = apps.get_model("api", "Message")
    Quiz = apps.get_model("quiz", "Quiz")
    Session = apps.get_model("quiz", "Session")
    SessionQuestion = apps.get_model("quiz", "SessionQuestion")
    SessionQuestionAnswer = apps.get_model("quiz", "SessionQuestionAnswer")
    UserQuiz = apps.get_model("quiz", "UserQuiz")
    QuizQuestion = Quiz.questions.through

    batch_size = 500  # Reduced batch size to lower memory usage

    # Step 1: Create Sessions in Bulk
    sessions_to_create = []
    quiz_ids = []
    quizzes_iterator = Quiz.objects.all().iterator(chunk_size=batch_size)

    for quiz in quizzes_iterator:
        session = Session(
            id=quiz.id,
            created_at=quiz.created_at,
            session_type="quiz",
            query=quiz.query,
            area=quiz.area,
            source_filter=quiz.source_filter,
            difficulty=quiz.difficulty,
            question_type=quiz.question_type,
            quiz_type=quiz.quiz_type,
            file=quiz.file,
            created_by=quiz.created_by,
            code=quiz.code,
            parent_session_id=quiz.parent_quiz_id,
        )
        sessions_to_create.append(session)
        quiz_ids.append(quiz.id)

        if len(sessions_to_create) >= batch_size:
            Session.objects.bulk_create(sessions_to_create, batch_size=batch_size)
            logger.info(f"Bulk created {len(sessions_to_create)} Session objects.")
            sessions_to_create = []

    # Create any remaining sessions
    if sessions_to_create:
        Session.objects.bulk_create(sessions_to_create, batch_size=batch_size)
        logger.info(
            f"Bulk created the final batch of {len(sessions_to_create)} Session objects."
        )

    # Step 2: Create SessionQuestions in Bulk
    # Process QuizQuestions in chunks to avoid loading all into memory
    quiz_questions_iterator = (
        QuizQuestion.objects.filter(quiz_id__in=quiz_ids)
        .order_by("sort_value")
        .iterator(chunk_size=batch_size)
    )
    session_questions_to_create = []

    for quiz_question in quiz_questions_iterator:
        session_question = SessionQuestion(
            session_id=quiz_question.quiz_id,
            question_id=quiz_question.question_id,
            order=quiz_question.sort_value,
        )
        session_questions_to_create.append(session_question)

        if len(session_questions_to_create) >= batch_size:
            SessionQuestion.objects.bulk_create(
                session_questions_to_create, batch_size=batch_size
            )
            logger.info(
                f"Bulk created {len(session_questions_to_create)} SessionQuestion objects."
            )
            session_questions_to_create = []

    # Create any remaining session questions
    if session_questions_to_create:
        SessionQuestion.objects.bulk_create(
            session_questions_to_create, batch_size=batch_size
        )
        logger.info(
            f"Bulk created the final batch of {len(session_questions_to_create)} SessionQuestion objects."
        )

    # Step 3: Create a Mapping of (session_id, question_id) to session_question_id
    # Use values to fetch only necessary fields and iterate to minimize memory usage
    session_question_map = {}
    session_questions_iterator = (
        SessionQuestion.objects.filter(session_id__in=quiz_ids)
        .values("id", "session_id", "question_id")
        .iterator(chunk_size=batch_size)
    )

    for sq in session_questions_iterator:
        session_question_map[(sq["session_id"], sq["question_id"])] = sq["id"]

    # Step 4: Create SessionQuestionAnswers in Bulk
    answers_to_create = []
    user_quizzes_iterator = (
        UserQuiz.objects.filter(quiz_id__in=quiz_ids)
        .prefetch_related(Prefetch("user_quiz_answer_set"))
        .iterator(chunk_size=batch_size)
    )

    for user_quiz in user_quizzes_iterator:
        session_id = user_quiz.quiz_id
        for answer in user_quiz.user_quiz_answer_set.all():
            session_question_id = session_question_map.get(
                (session_id, answer.question_id)
            )
            if not session_question_id:
                logger.warning(
                    f"Could not find session question for session {session_id} and question {answer.question_id}"
                )
                continue

            answers_to_create.append(
                SessionQuestionAnswer(
                    session_question_id=session_question_id,
                    user_id=user_quiz.user_id,
                    choice_id=answer.choice_id,
                    submitted_text=getattr(answer, "submitted_text", "") or "",
                    timestamp=getattr(answer, "timestamp", None),
                    feedback=getattr(answer, "feedback", "") or "",
                    grade=getattr(answer, "grade", None),
                )
            )

            if len(answers_to_create) >= batch_size:
                SessionQuestionAnswer.objects.bulk_create(
                    answers_to_create, batch_size=batch_size
                )
                logger.info(
                    f"Bulk created a batch of {len(answers_to_create)} SessionQuestionAnswer objects."
                )
                answers_to_create = []

    # Insert any remaining SessionQuestionAnswer instances
    if answers_to_create:
        SessionQuestionAnswer.objects.bulk_create(
            answers_to_create, batch_size=batch_size
        )
        logger.info(
            f"Bulk created the final batch of {len(answers_to_create)} SessionQuestionAnswer objects."
        )

    # Update messages with the corresponding session
    # The session was created with the same ID as the quiz in 0030_migrate_quiz_data
    for message in Message.objects.filter(quiz__isnull=False):
        message.session_id = message.quiz_id
        message.save(update_fields=["session"])

    for bonus_event in BonusEvent.objects.all():
        quiz_ids = bonus_event.quizzes.values_list("id", flat=True)
        bonus_event.sessions.add(*quiz_ids)  # The IDs are the same


def reverse_migrate_quiz_to_session(apps, schema_editor):
    """
    Reverse migration for migrate_quiz_to_session.
    Converts Session, SessionQuestion, and SessionQuestionAnswer back to Quiz, QuizQuestion, and UserQuizAnswer.
    """

    # Get the historical models
    BonusEvent = apps.get_model("bonus_events", "BonusEvent")
    Message = apps.get_model("api", "Message")
    Quiz = apps.get_model("quiz", "Quiz")
    Session = apps.get_model("quiz", "Session")
    SessionQuestion = apps.get_model("quiz", "SessionQuestion")
    SessionQuestionAnswer = apps.get_model("quiz", "SessionQuestionAnswer")
    UserQuiz = apps.get_model("quiz", "UserQuiz")
    UserQuizAnswer = apps.get_model("quiz", "UserQuizAnswer")
    QuizQuestion = Quiz.questions.through

    # Step 1: Create Quizzes from Sessions
    logger.info(
        "Starting reverse migration: Creating Quiz objects from Session objects."
    )

    sessions = Session.objects.filter(session_type="quiz").values(
        "id",
        "created_at",
        "query",
        "area",
        "source_filter",
        "difficulty",
        "question_type",
        "quiz_type",
        "file",
        "created_by",
        "code",
        "parent_session_id",
    )

    if not sessions.exists():
        logger.warning(
            "No Session objects of type 'quiz' found. Skipping Quiz creation."
        )
    else:
        # Prepare Quiz instances for bulk creation
        quizzes_to_create = [
            Quiz(
                id=session["id"],
                created_at=session["created_at"],
                query=session["query"],
                area=session["area"],
                source_filter=session["source_filter"],
                difficulty=session["difficulty"],
                question_type=session["question_type"],
                quiz_type=session["quiz_type"],
                file=session["file"],
                created_by_id=session[
                    "created_by"
                ],  # Use _id to avoid fetching the related object
                code=session["code"],
                parent_quiz_id=session[
                    "parent_session_id"
                ],  # Assuming parent_quiz_id corresponds to parent_session_id
            )
            for session in sessions
        ]

        if quizzes_to_create:
            try:
                with transaction.atomic():
                    Quiz.objects.bulk_create(quizzes_to_create)
                logger.info(f"Created {len(quizzes_to_create)} Quiz objects.")
            except IntegrityError as e:
                logger.error(f"IntegrityError during Quiz creation: {e}")
                raise

    # Step 2: Create QuizQuestions from SessionQuestions
    logger.info("Creating QuizQuestion objects from SessionQuestion objects.")

    session_questions = (
        SessionQuestion.objects.select_related("session", "question")
        .filter(session__session_type="quiz")
        .values("session_id", "question_id", "order")
    )

    if not session_questions.exists():
        logger.warning(
            "No SessionQuestion objects found for Sessions of type 'quiz'. Skipping QuizQuestion creation."
        )
    else:
        # Prepare QuizQuestion instances for bulk creation
        quiz_questions_to_create = [
            QuizQuestion(
                quiz_id=sq["session_id"],
                question_id=sq["question_id"],
                sort_value=sq["order"],  # Assuming sort_value corresponds to order
            )
            for sq in session_questions
        ]

        if quiz_questions_to_create:
            try:
                with transaction.atomic():
                    QuizQuestion.objects.bulk_create(quiz_questions_to_create)
                logger.info(
                    f"Created {len(quiz_questions_to_create)} QuizQuestion objects."
                )
            except IntegrityError as e:
                logger.error(f"IntegrityError during QuizQuestion creation: {e}")
                raise

    # Step 3: Create UserQuizAnswers from SessionQuestionAnswers
    logger.info("Creating UserQuizAnswer objects from SessionQuestionAnswer objects.")

    session_question_answers = SessionQuestionAnswer.objects.select_related(
        "session_question__session", "user", "choice"
    ).filter(session_question__session__session_type="quiz")

    if not session_question_answers.exists():
        logger.warning(
            "No SessionQuestionAnswer objects found for Sessions of type 'quiz'. Skipping UserQuizAnswer creation."
        )
    else:
        user_quiz_pairs = set(
            session_question_answers.values_list(
                "user_id", "session_question__session_id"
            )
        )

        user_quizzes_to_create = [
            UserQuiz(user_id=pair[0], quiz_id=pair[1]) for pair in user_quiz_pairs
        ]

        user_quiz_map = {}

        if user_quizzes_to_create:
            try:
                with transaction.atomic():
                    created_user_quizzes = UserQuiz.objects.bulk_create(
                        user_quizzes_to_create
                    )
                # Update the map with newly created UserQuiz entries
                for uq in created_user_quizzes:
                    user_quiz_map[(uq.user_id, uq.quiz_id)] = uq.id
                logger.info(f"Created {len(created_user_quizzes)} UserQuiz objects.")
            except IntegrityError as e:
                logger.error(f"IntegrityError during UserQuiz creation: {e}")
                raise

        # **Optimization 4: Preparing UserQuizAnswer Instances in Batches**
        answers_to_create = []
        batch_size = 1000  # Adjust based on memory and database capacity

        # Using iterator() to handle large QuerySets efficiently
        for sqa in session_question_answers.iterator():
            user_quiz_id = user_quiz_map.get(
                (sqa.user_id, sqa.session_question.session_id)
            )
            if not user_quiz_id:
                logger.error(
                    f"UserQuiz not found for user {sqa.user_id} and quiz {sqa.session_question.session_id}. Skipping."
                )
                continue  # Or handle appropriately

            answers_to_create.append(
                UserQuizAnswer(
                    user_quiz_id=user_quiz_id,
                    question_id=sqa.session_question.question_id,
                    choice_id=sqa.choice_id,  # Use _id to avoid fetching the related object
                    submitted_text=sqa.submitted_text,
                    timestamp=sqa.timestamp,
                    feedback=sqa.feedback,
                    grade=sqa.grade,
                )
            )

            # Bulk insert in batches
            if len(answers_to_create) >= batch_size:
                try:
                    with transaction.atomic():
                        UserQuizAnswer.objects.bulk_create(answers_to_create)
                    logger.info(
                        f"Created a batch of {len(answers_to_create)} UserQuizAnswer objects."
                    )
                    answers_to_create = []
                except IntegrityError as e:
                    logger.error(f"IntegrityError during UserQuizAnswer creation: {e}")
                    raise

        # Insert any remaining UserQuizAnswer instances
        if answers_to_create:
            try:
                with transaction.atomic():
                    UserQuizAnswer.objects.bulk_create(answers_to_create)
                logger.info(
                    f"Created the final batch of {len(answers_to_create)} UserQuizAnswer objects."
                )
            except IntegrityError as e:
                logger.error(
                    f"IntegrityError during final UserQuizAnswer creation: {e}"
                )
                raise

    logger.info("Reverse migration completed successfully.")

    for message in Message.objects.filter(session__isnull=False):
        message.quiz_id = message.session_id
        message.save(update_fields=["quiz"])

    for bonus_event in BonusEvent.objects.all():
        session_ids = bonus_event.sessions.values_list("id", flat=True)
        bonus_event.quizzes.add(*session_ids)


class Migration(migrations.Migration):
    dependencies = [
        ("quiz", "0029_add_session_models"),
        ("api", "0024_remove_message_quiz_message_session"),
        ("bonus_events", "0003_remove_bonusevent_quizzes_bonusevent_sessions"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quiz",
            name="created_at",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="userquizanswer",
            name="timestamp",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="session",
            name="created_at",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="sessionquestionanswer",
            name="timestamp",
            field=models.DateTimeField(),
        ),
        migrations.RunPython(migrate_quiz_to_session, reverse_migrate_quiz_to_session),
        migrations.AlterField(
            model_name="quiz",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="userquizanswer",
            name="timestamp",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="session",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="sessionquestionanswer",
            name="timestamp",
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]
