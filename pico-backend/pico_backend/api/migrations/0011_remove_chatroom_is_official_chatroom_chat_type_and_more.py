from django.db import migrations, models


def update_chat_type(apps, schema_editor):
    Chatroom = apps.get_model("api", "Chatroom")
    chatrooms = Chatroom.objects.all()
    updated_chatrooms = []

    for chatroom in chatrooms:
        chatroom.chat_type = 2 if chatroom.is_official else 0
        updated_chatrooms.append(chatroom)

    # Perform a bulk update
    Chatroom.objects.bulk_update(updated_chatrooms, ["chat_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0010_message_quiz"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatroom",
            name="chat_type",
            field=models.IntegerField(
                choices=[(0, "Group"), (1, "Dm"), (2, "Official")], default=0
            ),
        ),
        migrations.RunPython(update_chat_type),
        migrations.RemoveField(
            model_name="chatroom",
            name="is_official",
        ),
        migrations.AlterField(
            model_name="chatroom",
            name="name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
