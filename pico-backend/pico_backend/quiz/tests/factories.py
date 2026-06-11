import factory

from quiz.models import (
    ENEM_AREAS,
    Choice,
    Question,
    QuestionSelectionMethod,
    Quiz,
    QuizType,
)

QUERIES = [
    "What is the capital of France?",
    "Quem sou eu?",
    "Como você é?",
    "O que você acha?",
    "minha história",
    "minha vida",
    "lesgoooooo",
    "what is love",
    "baby don't hurt me",
    "no more",
]


class ChoiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Choice

    text = factory.Faker("sentence")
    is_correct = factory.Iterator([True, False, True, False, False, True])
    question = factory.SubFactory("quiz.tests.factories.QuestionFactory")


class QuestionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Question

    text = factory.Faker("sentence")
    embedding = factory.Faker("random_elements", elements=[0.0, 1.0], length=1024)
    subject = factory.Faker("sentence")
    source = factory.Faker("sentence")
    difficulty = factory.Iterator(["", "Fácil", "Média", "Difícil"])
    image = factory.django.ImageField(color="blue")
    answer_image = factory.django.ImageField(color="red")
    video_url = factory.Faker("url")
    is_fast = factory.Iterator([True, False, True, False, False, True])

    @classmethod
    def create_batch_multiple_choice(cls, size, **kwargs):
        questions = super().create_batch(size, **kwargs)
        for question in questions:
            # Create 4 incorrect choices
            ChoiceFactory.create_batch(4, question=question, is_correct=False)
            # Create 1 correct choice
            ChoiceFactory.create(question=question, is_correct=True)
        return questions


class QuizFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Quiz

    query = factory.Iterator(QUERIES)
    area = factory.Iterator(ENEM_AREAS.keys())
    source_filter = "ENEM"
    quiz_type = QuizType.QUERY_BASED
    selection_method = QuestionSelectionMethod.QUERY_OFFICIAL
