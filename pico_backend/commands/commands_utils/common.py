import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import api.services.message_service as message_service
from api.models import Chatroom, EmbeddedFile, FileGroup, Message, User
from django.core.files import File as DjangoFile

logger = logging.getLogger(__name__)


def extract_command_text(query: str) -> str:
    """
    Extract the command text, assuming the command prefix '/' is always present.
    """
    # Simply split by the first space and return the rest, if any
    return query.split(" ", 1)[1].strip() if " " in query else ""


def get_embedded_file_from_command_text(
    command_text: str, chatroom: Chatroom
) -> EmbeddedFile | None:
    """
    Adjusted function to extract embedded file based on a reference within the command text,
    accounting for the format "# <number>".
    """
    try:
        # Adjusted to account for space: "# <number>"
        file_index = int(command_text[2:].split()[0]) - 1  # Skip "# " then split
        return EmbeddedFile.objects.filter(
            messages__chatroom=chatroom, file_processing_done=True
        ).order_by("messages__timestamp")[file_index]
    except (ValueError, IndexError):
        return None


def get_file_group_from_command_text(command_text: str) -> FileGroup | None:
    """
    Simplify the retrieval of FileGroup based on the command text.
    """
    try:
        # Directly attempt to fetch the FileGroup without pre-checks
        file_group_name = command_text.split(" ", 1)[0]
        return FileGroup.objects.get(name=file_group_name)
    except (FileGroup.DoesNotExist, IndexError):
        return None


@dataclass
class CommandContext:
    chatroom: Chatroom
    query: str
    user: User
    parent_message: Message | None = None

    @property
    def command_text(self) -> str:
        return extract_command_text(self.query)


class CommandHandler(ABC):
    cmd: str
    description: str = ""
    generate_embedding: bool = True
    thread_command: bool = False
    main_chat_command: bool = True

    def __init__(self, context: CommandContext):
        self.context = context
        if (
            self.thread_command
            and not self.main_chat_command
            and not context.parent_message
        ):
            raise ValueError("Parent message is required for thread commands.")
        if (
            self.main_chat_command
            and not self.thread_command
            and context.parent_message is not None
        ):
            raise ValueError(
                "No parent message should be provided for main chat commands."
            )

    def handle(self):
        """
        Template method that handles the command.
        Includes error handling.
        Calls the abstract method 'execute_command' for the actual command logic.
        """
        logger.debug(f"Handling command: '{self.cmd}' with context: {self.context}")
        try:
            self.execute_command()
            logger.debug(
                f"Successfully handled command: '{self.cmd}' with context: {self.context}."
            )
        except Exception as e:
            logger.error(f"Error in {self.__class__.__name__}: {e}", exc_info=True)
            return "Desculpe, tive um problema com seu comando!"

    @abstractmethod
    def execute_command(self):
        """
        Abstract method to be implemented by subclasses for actual command logic.
        """
        ...

    def send_message(self, message: str):
        message_service.send_message(
            sender="pico",
            chatroom=self.context.chatroom,
            content=message,
            parent_message=self.context.parent_message,
            have_embedding=self.generate_embedding,
        )

    def send_message_with_attachment(self, message: str, attachment: DjangoFile):
        message_service.send_message(
            sender="pico",
            chatroom=self.context.chatroom,
            content=message,
            parent_message=self.context.parent_message,
            have_embedding=self.generate_embedding,
            attachment=attachment,
        )


# CommandRegistry: Manages the registration and retrieval of command handlers
class CommandRegistry:
    _registry: dict[str, type[CommandHandler]] = {}

    @classmethod
    def register(
        cls,
        handler_class: type[CommandHandler],
    ) -> None:
        if not hasattr(handler_class, "cmd") or not isinstance(handler_class.cmd, str):
            raise ValueError(
                f"Handler class '{handler_class.__name__}' does not have a 'cmd' string attribute."
            )
        elif not handler_class.cmd.startswith("/"):
            raise ValueError(
                f"Handler class '{handler_class.__name__}' does not have a 'cmd' attribute that starts with '/'."
            )
        cls._registry[handler_class.cmd] = handler_class

    @classmethod
    def get_handler(
        cls,
        cmd: str,
        chatroom: Chatroom,
        parent_message: Message | None,
        query: str,
        user: User,
    ) -> CommandHandler | None:
        if cmd not in cls._registry:
            logger.debug(f"Command not found: {cmd}")
            return None
        else:
            handler_class = cls._registry[cmd]
            logger.debug(f"Command found: {cmd}, handler: {handler_class.__name__}")
            context = CommandContext(
                chatroom=chatroom, parent_message=parent_message, query=query, user=user
            )
            return handler_class(context)

    @classmethod
    def get_commands_and_descriptions(cls) -> list[tuple[str, str]]:
        return [
            (cmd, handler_class.description)
            for cmd, handler_class in cls._registry.items()
        ]


def register_command(cls: type[CommandHandler]) -> type[CommandHandler]:
    if not hasattr(cls, "cmd") or not cls.cmd.startswith("/"):
        raise ValueError(
            f"Command '{cls.__name__}' must have a 'cmd' attribute that starts with '/'."
        )
    CommandRegistry.register(cls)
    return cls
