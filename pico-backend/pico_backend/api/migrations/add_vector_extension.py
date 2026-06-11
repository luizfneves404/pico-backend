from pgvector.django import VectorExtension
from django.db import migrations


class Migration(migrations.Migration):
    run_before = [
        (
            "api",
            "0001_initial",
        ),  # change to the name of the first migration file
    ]
    operations = [VectorExtension()]
