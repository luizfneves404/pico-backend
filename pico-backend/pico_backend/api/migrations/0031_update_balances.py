from django.db import migrations


def update_balances(apps, schema_editor):
    User = apps.get_model("api", "User")
    User.objects.all().update(balance=1000)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0030_alter_chatroom_icon"),
    ]

    operations = [
        migrations.RunPython(update_balances, migrations.RunPython.noop),
    ]
