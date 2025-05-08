from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_remove_quiz_unique_query_subject_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quiz",
            name="questions",
            field=models.ManyToManyField(
                help_text=None,
                related_name="quizzes",
                to="core.question",
            ),
        ),
    ]
