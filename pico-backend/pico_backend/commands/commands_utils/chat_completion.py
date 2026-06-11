import logging
from dataclasses import dataclass

from api.models import Chatroom, EmbeddedFile, FileGroup, Message
from django.conf import settings
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
)
from shared import openai_utils

from commands.commands_utils.embeddings import (  # search_similar_messages,
    search_similar_text_chunks_in_all_files,
    search_similar_text_chunks_in_file,
    search_similar_text_chunks_in_file_group,
)

logger = logging.getLogger(__name__)

# Constants
API_KEY = settings.OPENAI_API_KEY


client = OpenAI(api_key=API_KEY, timeout=90, max_retries=2)


@dataclass
class SystemMessageStrategy:
    def __call__(self) -> ChatCompletionSystemMessageParam:
        raise NotImplementedError


@dataclass
class FixedSystemMessageStrategy(SystemMessageStrategy):
    system_message_str: str

    def __call__(self) -> ChatCompletionSystemMessageParam:
        return create_system_message(self.system_message_str)


@dataclass
class FileSystemMessageStrategy(SystemMessageStrategy):
    system_message_str: str
    embedded_file: EmbeddedFile
    search_text: str
    n_similar: int

    def __call__(self) -> ChatCompletionSystemMessageParam:
        similar_text_chunks = search_similar_text_chunks_in_file(
            self.n_similar, self.search_text, self.embedded_file
        )
        similar_text_chunks_text = "\n".join(
            [f"- {chunk.text}" for chunk in similar_text_chunks]
        )
        return create_system_message(
            self.system_message_str.format(context=similar_text_chunks_text)
        )


@dataclass
class FileGroupSystemMessageStrategy(SystemMessageStrategy):
    system_message_str: str
    file_group: FileGroup
    search_text: str
    n_similar: int

    def __call__(self) -> ChatCompletionSystemMessageParam:
        similar_text_chunks = search_similar_text_chunks_in_file_group(
            self.n_similar, self.search_text, self.file_group
        )
        similar_text_chunks = [chunk[1] for chunk in similar_text_chunks]
        similar_text_chunks_text = "\n".join(
            [f"- {chunk}" for chunk in similar_text_chunks]
        )
        return create_system_message(
            self.system_message_str.format(context=similar_text_chunks_text)
        )


@dataclass
class LocalAndGlobalFilesSystemMessageStrategy(SystemMessageStrategy):
    system_message_str: str
    chatroom: Chatroom
    search_text: str
    n_similar: int

    def __call__(self) -> ChatCompletionSystemMessageParam:
        similar_text_chunks = search_similar_text_chunks_in_all_files(
            self.n_similar, self.search_text, self.chatroom
        )
        similar_text_chunks = [chunk[1] for chunk in similar_text_chunks]
        similar_text_chunks_text = "\n".join(
            [f"- {chunk}" for chunk in similar_text_chunks]
        )
        return create_system_message(
            self.system_message_str.format(context=similar_text_chunks_text)
        )


@dataclass
class RecentMessagesStrategy:
    """max_context_tokens: int
    maximum amount of tokens that __call__ should return

    Raises:
        ValueError: _description_
        NotImplementedError: _description_

    Returns:
        _type_: _description_
    """

    max_context_tokens: int

    def __call__(self) -> list[ChatCompletionMessageParam]:
        if self.max_context_tokens < 0:
            raise ValueError("The user message is too long for the context tokens")
        return self.execute()

    def execute(self) -> list[ChatCompletionMessageParam]:
        raise NotImplementedError


@dataclass
class NRecentMessagesStrategy(RecentMessagesStrategy):
    chatroom: Chatroom
    max_messages: int

    def execute(self) -> list[ChatCompletionMessageParam]:
        return get_recent_messages(
            self.chatroom, self.max_messages, self.max_context_tokens
        )


@dataclass
class OneMessageRecentMessagesStrategy(RecentMessagesStrategy):
    user_message_content: str

    def execute(self) -> list[ChatCompletionMessageParam]:
        user_message_tokens = openai_utils.count_tokens(self.user_message_content)
        if user_message_tokens > self.max_context_tokens:
            raise ValueError("The user message is too long for the context tokens")
        return [{"role": "user", "content": self.user_message_content}]


@dataclass
class Chatbot:
    system_message_strategy: SystemMessageStrategy
    recent_messages_strategy: RecentMessagesStrategy

    def get_response(
        self,
        chat_model: str,
        temperature: float,
        timeout: int = 90,
    ) -> str:
        system_message = self.system_message_strategy()
        starting_tokens = openai_utils.count_tokens(str(system_message["content"]))
        self.recent_messages_strategy.max_context_tokens -= starting_tokens

        messages = self.recent_messages_strategy()
        messages.insert(0, system_message)
        return openai_utils.get_completion(
            chat_model, temperature, messages, json_mode=False, timeout=timeout
        ).content


def create_system_message(system_message: str) -> ChatCompletionSystemMessageParam:
    """Create a system message for initializing the chat."""
    return {"role": "system", "content": system_message}


def format_message(msg: Message) -> list[ChatCompletionMessageParam]:
    """Format a single message for the chatbot. Should have fields "sender" and "embedded_files" prefetched."""
    role = "assistant" if msg.sender.username == "pico" else "user"
    formatted_messages = []

    if msg.embedded_files.exists():
        for embedded_file in msg.embedded_files.all():
            filename = embedded_file.file.name.split("/")[-1]
            formatted_messages.append(
                {
                    "role": "user",
                    "content": f"User '{msg.sender.username}' sent a file named '{filename}'",
                }
            )

    if msg.content:
        content = (
            f"{msg.sender.username}: {msg.content}" if role == "user" else msg.content
        )
        formatted_messages.append({"role": role, "content": content})

    return formatted_messages


def query_messages(chatroom: Chatroom):
    """Query top-level messages from the database."""
    return (
        Message.objects.filter(chatroom=chatroom, parent_message=None)
        .select_related("sender")
        .prefetch_related("embedded_files")
        .order_by("timestamp")
    )


def query_messages_reversed(chatroom: Chatroom):
    return query_messages(chatroom).reverse()


def get_recent_messages(
    chatroom: Chatroom, max_messages: int, max_context_tokens: int
) -> list[ChatCompletionMessageParam]:
    """Get the most recent messages from the chatroom, up to a maximum number
    of messages and context tokens. The messages are formatted for the chatbot.

    Args:
        chatroom (Chatroom): the chatroom to query
        max_messages (int): the maximum amount of messages to return
        max_context_tokens (int): the maximum amount of tokens to return in total

    Returns:
        list[ChatCompletionMessageParam]: a list of formatted messages
    """
    queried_messages_reversed = query_messages_reversed(chatroom)
    messages = []

    total_tokens = 0

    for msg in queried_messages_reversed:
        formatted_messages = format_message(msg)
        for formatted_message in formatted_messages:
            message_tokens = openai_utils.count_tokens(formatted_message["content"])
            if (
                len(messages) < max_messages
                and total_tokens + message_tokens <= max_context_tokens
            ):
                messages.insert(0, formatted_message)
                total_tokens += message_tokens
            else:
                # Stop adding more messages if the limit is reached
                break
    return messages


""" def get_max_recent_messages_context(
    system_message_str: str,
    maximum_context_tokens: int,
    chatroom: Chatroom,
):
    system_message = create_system_message(system_message_str)
    total_tokens = text_to_num_tokens_cl100k_base(system_message["content"])
    new_messages_reversed = query_messages_reversed(chatroom)

    messages = []

    for msg in new_messages_reversed:
        formatted_messages = format_message(msg)
        for formatted_message in formatted_messages:
            message_tokens = openai_utils.text_to_num_tokens_cl100k_base(
                formatted_message["content"]
            )
            if total_tokens + message_tokens <= maximum_context_tokens:
                messages.insert(0, formatted_message)
                total_tokens += message_tokens
            else:
                # Stop adding more messages if the limit is reached
                break

    messages.insert(0, system_message)

    return messages """


""" def get_fixed_recent_messages_context(
    system_message_str: str,
    max_messages: int,
    max_context_tokens: int,
    chatroom: Chatroom,
):
    system_message = create_system_message(system_message_str)
    starting_tokens = text_to_num_tokens_cl100k_base(system_message["content"])

    messages = get_recent_messages(
        chatroom, max_messages, max_context_tokens - starting_tokens
    )

    messages.insert(0, system_message)

    return messages """


""" def get_similar_messages_context(
    message_context_system_message_str: str,
    chatroom: Chatroom,
    n_similar: int,
    search_text: str,
):
    similar_messages = search_similar_messages(n_similar, search_text, chatroom)
    similar_messages_text = "\n".join(
        [f"- {msg.sender.username}: {msg.content}" for msg in similar_messages]
    )
    system_message = create_system_message(
        message_context_system_message_str.format(context=similar_messages_text)
    )

    messages = [system_message]

    messages.append({"role": "user", "content": search_text})

    return messages """


""" def get_similar_text_chunks_context(
    file_context_system_message_str: str,
    embedded_file: EmbeddedFile,
    n_similar: int,
    search_text: str,
):
    similar_text_chunks = search_similar_text_chunks_in_file(
        n_similar, search_text, embedded_file
    )
    similar_text_chunks_text = "\n".join(
        [f"- {chunk.text}" for chunk in similar_text_chunks]
    )
    system_message = create_system_message(
        file_context_system_message_str.format(context=similar_text_chunks_text)
    )

    messages = [system_message]

    messages.append({"role": "user", "content": search_text})

    return messages """


""" def get_similar_text_chunks_context_file_group(
    file_context_system_message_str: str,
    file_group: FileGroup,
    n_similar: int,
    search_text: str,
):
    similar_text_chunks = search_similar_text_chunks_in_file_group(
        n_similar, search_text, file_group
    )
    similar_text_chunks = [chunk[1] for chunk in similar_text_chunks]
    similar_text_chunks_text = "\n".join(
        [f"- {chunk}" for chunk in similar_text_chunks]
    )
    system_message = create_system_message(
        file_context_system_message_str.format(context=similar_text_chunks_text)
    )

    messages = [system_message]

    messages.append({"role": "user", "content": search_text})

    return messages """


""" def get_similar_text_chunks_and_recent_messages_context(
    file_context_system_message_str: str,
    n_similar: int,
    search_text: str,
    max_messages: int,
    max_context_tokens: int,
    chatroom: Chatroom,
) -> list[dict[str, str]]:
    similar_text_chunks = search_similar_text_chunks_in_all_files(
        n_similar, search_text, chatroom
    )
    similar_text_chunks = [chunk[1] for chunk in similar_text_chunks]
    similar_text_chunks_text = "\n".join(
        [f"- {chunk}" for chunk in similar_text_chunks]
    )
    system_message = create_system_message(
        file_context_system_message_str.format(context=similar_text_chunks_text)
    )

    starting_tokens = text_to_num_tokens_cl100k_base(system_message["content"])
    messages = get_recent_messages(
        chatroom, max_messages, max_context_tokens - starting_tokens
    )

    messages.insert(0, system_message)

    return messages """


""" def get_chatbot_response_with_max_recent_messages_context(
    system_message_str: str,
    maximum_context_tokens: int,
    chat_model: str,
    temperature: float,
    chatroom: Chatroom,
) -> str:
    messages = get_max_recent_messages_context(
        system_message_str, maximum_context_tokens, chatroom
    )

    return call_openai_chat_completions_create(chat_model, temperature, messages) """


""" def get_chatbot_response_with_fixed_recent_messages_context(
    system_message_str: str,
    max_messages: int,
    max_context_tokens: int,
    chat_model: str,
    temperature: float,
    chatroom: Chatroom,
) -> str:
    messages = get_fixed_recent_messages_context(
        system_message_str, max_messages, max_context_tokens, chatroom
    )

    return call_openai_chat_completions_create(chat_model, temperature, messages)
 """

""" def get_chatbot_response_no_context(
    system_message_str: str, chat_model: str, temperature: float, user_message: str
) -> str:
    messages = [create_system_message(system_message_str)]
    messages.append({"role": "user", "content": user_message})
    return call_openai_chat_completions_create(chat_model, temperature, messages) """


""" def get_chatbot_response_with_similar_messages_context(
    message_context_system_message_str: str,
    chat_model: str,
    temperature: float,
    n_similar: int,
    chatroom: Chatroom,
    search_text: str,
) -> str:
    messages = get_similar_messages_context(
        message_context_system_message_str, chatroom, n_similar, search_text
    )

    return call_openai_chat_completions_create(chat_model, temperature, messages) """


""" def get_chatbot_response_with_file_context(
    file_context_system_message_str: str,
    chat_model: str,
    temperature: float,
    n_similar: int,
    embedded_file: EmbeddedFile,
    search_text: str,
) -> str:
    messages = get_similar_text_chunks_context(
        file_context_system_message_str, embedded_file, n_similar, search_text
    )

    return call_openai_chat_completions_create(chat_model, temperature, messages) """


""" def get_chatbot_response_with_file_group_context(
    file_context_system_message_str: str,
    chat_model: str,
    temperature: float,
    n_similar: int,
    file_group: FileGroup,
    search_text: str,
) -> str:
    messages = get_similar_text_chunks_context_file_group(
        file_context_system_message_str, file_group, n_similar, search_text
    )

    return call_openai_chat_completions_create(chat_model, temperature, messages) """


""" def get_chatbot_response_with_all_files_and_recent_messages_context(
    file_context_system_message_str: str,
    chat_model: str,
    temperature: float,
    n_similar: int,
    search_text: str,
    max_messages: int,
    max_context_tokens: int,
    chatroom: Chatroom,
) -> str:
    messages = get_similar_text_chunks_and_recent_messages_context(
        file_context_system_message_str,
        n_similar,
        search_text,
        max_messages,
        max_context_tokens,
        chatroom,
    )

    return call_openai_chat_completions_create(chat_model, temperature, messages) """
