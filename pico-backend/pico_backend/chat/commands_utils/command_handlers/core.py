<<<<<<< HEAD
=======
from .base import (
    MaxRecentMessagesContextCommandHandler,
    FixedRecentMessagesContextCommandHandler,
    NoContextCommandHandler,
    FileContextCommandHandler,
    MessageSearchCommandHandler,
    SimilarMessagesContextCommandHandler,
    FileSearchCommandHandler,
    SpecificFilesSearchCommandHandler,
    SpecificFileContextCommandHandler,
)
from ..common import register_command, CommandHandler, CommandRegistry
from ..chatroom import format_member_list, format_files_list

CHAT_MODEL = "gpt-3.5-turbo-0125"
MAXIMUM_CONTEXT_LENGTH = 2097
VANILLA_SYSTEM_MESSAGE = (
    "You are Pico, a smart chatbot that can talk about "
    "anything. You should act as a friendly AI tutor that "
    "helps users learn about the topics they request. "
    "Every message by a user will be prefixed by their "
    "username, so that you know who sent the message. "
    "If a message is preceded by '/pico', this means that "
    "the user is calling you to answer them. Some messages "
    "may represent a file being sent to you by a user. "
    "Promote learning, curiosity and kindness."
)
MESSAGE_CONTEXT_SYSTEM_MESSAGE = (
    "You are Pico, a smart chatbot that can talk about "
    "anything. "
    "Look for an answer to the user's question in the context of the following messages, "
    "enclosed in triple quotes:\n"
    "'''\n{context}\n'''\n"
    "Then, answer the user's question."
)
FILE_CONTEXT_SYSTEM_MESSAGE = (
    "You are Pico, a smart chatbot that can talk about "
    "anything. "
    "Look for an answer to the user's question in the context of the following text chunks, "
    "enclosed in triple quotes:\n"
    "'''\n{context}\n'''\n"
    "Then, answer the user's question."
)
ROADMAP_SYSTEM_MESSAGE = (
    "You an expert teacher in a variety of subjects. You will be prompted to write a roadmap "
    "for a user to learn about a topic of their choice. "
    "The message sent by the user will have the following format: "
    "'/pico_roadmap <topic>'."
    "There is no need to talk directly to the user. You should "
    "respond with a long and comprehensive roadmap that contains the following information: "
    "A list of subtopics that the user should learn about, in the order that they should be learned. "
    "For each subtopic, provide a list of resources that the user can use to learn about the subtopic. "
)
FILE_NOT_READY_MESSAGE = (
    "I haven't looked into that file yet. "
    "If it is not a PDF, or if I said I wouldn't process it, then it "
    "won't be processed."
)
FILE_NOT_FOUND_MESSAGE = (
    "I couldn't find your file. Write the file number after the command, "
    "like this: /file_ask # 1"
)
NUMBER_OF_SIMILAR_EMBEDDINGS = 4
NUMBER_OF_SIMILAR_TEXT_CHUNK_EMBEDDINGS = 4


@register_command
class PicoCommandHandler(MaxRecentMessagesContextCommandHandler):
    cmd = "/pico"
    system_message = VANILLA_SYSTEM_MESSAGE
    maximum_context_tokens = MAXIMUM_CONTEXT_LENGTH
    chat_model = CHAT_MODEL


@register_command
class PicoRoadmapCommandHandler(NoContextCommandHandler):
    cmd = "/pico_roadmap"
    system_message = ROADMAP_SYSTEM_MESSAGE
    chat_model = CHAT_MODEL


@register_command
class PicoSimilarMessagesCommandHandler(SimilarMessagesContextCommandHandler):
    cmd = "/ask"
    system_message = MESSAGE_CONTEXT_SYSTEM_MESSAGE
    chat_model = CHAT_MODEL
    n_similar = NUMBER_OF_SIMILAR_EMBEDDINGS


@register_command
class PicoMessageSearchCommandHandler(MessageSearchCommandHandler):
    cmd = "/search"
    n_similar = NUMBER_OF_SIMILAR_EMBEDDINGS


@register_command
class PicoFileContextCommandHandler(FileContextCommandHandler):
    cmd = "/file_ask"
    system_message = FILE_CONTEXT_SYSTEM_MESSAGE
    chat_model = CHAT_MODEL
    file_not_found_message = FILE_NOT_FOUND_MESSAGE
    file_not_ready_message = FILE_NOT_READY_MESSAGE
    n_similar = NUMBER_OF_SIMILAR_TEXT_CHUNK_EMBEDDINGS


@register_command
class PicoFileSearchCommandHandler(FileSearchCommandHandler):
    cmd = "/file_search"
    file_not_found_message = FILE_NOT_FOUND_MESSAGE
    file_not_ready_message = FILE_NOT_READY_MESSAGE
    n_similar = NUMBER_OF_SIMILAR_TEXT_CHUNK_EMBEDDINGS


@register_command
class HelpCommandHandler(CommandHandler):
    cmd = "/help"
    generate_embedding = False

    async def execute_command(self) -> str:
        """
        Handles the help command by providing a list of available commands and their categories.

        Returns a formatted help message with command listings.

        :return: Formatted help message.
        """
        help_message = [
            "'File thread commands' can only be called from threads.",
            "'Main chat commands' can only be called from the main chat.",
        ]

        for command, handler_class in CommandRegistry._registry.items():
            if handler_class.thread_command and handler_class.main_chat_command:
                command_type = "File thread command and main chat command"
            elif handler_class.thread_command:
                command_type = "File thread command"
            else:
                command_type = "Main chat command"

            help_message.append(f"{command} - {command_type}")

        return "\n".join(help_message)


@register_command
class MembersCommandHandler(CommandHandler):
    cmd = "/members"
    generate_embedding = False

    async def execute_command(self) -> str:
        """
        Handles the Pico command.

        Returns a chatbot response if successful, otherwise returns an error message.

        :return: The response string from the chatbot or an error message.
        """

        return await format_member_list(self.chatroom)


@register_command
class FilesCommandHandler(CommandHandler):
    cmd = "/files"
    generate_embedding = False

    async def execute_command(self) -> str:
        """
        Handles the Pico command.

        Returns a chatbot response if successful, otherwise returns an error message.

        :return: The response string from the chatbot or an error message.
        """

        return await format_files_list(self.chatroom)


# EXAMPLE: UN SPECIFIC FILE COMMAND HANDLER
@register_command
class UNSpecificFileSearchCommandHandler(SpecificFilesSearchCommandHandler):
    cmd = "/un_search"
    n_similar = NUMBER_OF_SIMILAR_TEXT_CHUNK_EMBEDDINGS
    attachment_message_content = "UN FILE"  # this should be input as well when uploading the csv for the embeddings


@register_command
class UNSpecificFileContextCommandHandler(SpecificFileContextCommandHandler):
    cmd = "/un_ask"
    system_message = FILE_CONTEXT_SYSTEM_MESSAGE
    chat_model = CHAT_MODEL
    n_similar = NUMBER_OF_SIMILAR_TEXT_CHUNK_EMBEDDINGS
    attachment_message_content = "UN FILE"
>>>>>>> parent of 9893707 (New function)
