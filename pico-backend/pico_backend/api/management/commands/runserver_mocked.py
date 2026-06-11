from daphne.management.commands.runserver import Command as RunserverCommand
from shared.mock import mock_external_apis


class Command(RunserverCommand):
    help = "Runs the Django development server with some external APIs mocked."

    def handle(self, *args, **options):
        with mock_external_apis():
            # Call the superclass handle method, which in turn starts the server
            super().handle(*args, **options)
