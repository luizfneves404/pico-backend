import json
import logging
from collections.abc import Callable
from typing import Any, TypeAlias, TypedDict

import httpx
from amplitude import Amplitude, BaseEvent
from fastapi import Request, Response
from httpx import BasicAuth

from app.config import settings

AMPLITUDE_FLUSH_QUEUE_SIZE = 10

AMPLITUDE_MIN_ID_LENGTH = 1

AMPLITUDE_DELETION_URL = "https://amplitude.com/api/2/deletions/users"
# Maximum body size for request data processing
MAX_BODY_SIZE = 1 * 1000 * 1000  # 1 MB
ANONYMOUS_EVENT_TYPES = [
    "POST user_create",
]

Properties: TypeAlias = dict[str, Any]
RequestData: TypeAlias = dict[str, Any]
ResponseData: TypeAlias = dict[str, Any]


PropsHandler = Callable[[Request, RequestData, ResponseData], Properties]
logger = logging.getLogger(__name__)

headers = {"Content-Type": "application/json", "Accept": "application/json"}
auth = BasicAuth(
    username=settings.amplitude_api_key, password=settings.amplitude_secret_key
)


class EventInfo(TypedDict):
    user_props_handler: PropsHandler | None
    event_props_handler: PropsHandler | None


event_name_to_info: dict[str, EventInfo] = {}


async def delete_user(user_id: int) -> None:
    if settings.amplitude_track_events:
        await _delete_user_from_amplitude(user_id)
    else:
        logger.debug(f"Would delete user {user_id} from Amplitude if tracking was on")


async def _delete_user_from_amplitude(
    user_id: int, retry_count: int = 0, max_retries: int = 5
) -> None:
    payload = json.dumps({"user_ids": [str(user_id)]})
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                AMPLITUDE_DELETION_URL, headers=headers, content=payload, auth=auth
            )
            response.raise_for_status()
            logger.info(
                f"User {user_id} was successfully deleted from Amplitude, response: {response.text}"
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"Error deleting user {user_id} from Amplitude: {e}")
            if e.response.status_code == 429 and retry_count < max_retries:
                logger.info(
                    f"Retrying deletion from Amplitude for user {user_id} in 60 seconds, because there were too many requests"
                )
                await _delete_user_from_amplitude(user_id, retry_count + 1, max_retries)
            elif e.response.status_code == 400:
                logger.error(
                    f"Bad Request to Amplitude user deletion, User {user_id} probably doesn't exist in Amplitude, response: {e.response.text}"
                )


def amplitude_callback(event: BaseEvent, code: int, message: str | None) -> None:
    if code != 200:
        logger.error(f"Amplitude error for event {event}: {code} {message}")


class AmplitudeClientSingleton:
    _instance: Amplitude | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = Amplitude(settings.amplitude_api_key)
            cls._instance.configuration.flush_queue_size = AMPLITUDE_FLUSH_QUEUE_SIZE
            cls._instance.configuration.callback = amplitude_callback
            cls._instance.configuration.min_id_length = AMPLITUDE_MIN_ID_LENGTH
        return cls._instance


class MockAmplitudeClient:
    def track(self, event: BaseEvent) -> None:
        logger.debug(
            "Did not track event {event.event_type} for user {event.user_id} because tracking is disabled"
        )


def get_amplitude_client():
    return (
        AmplitudeClientSingleton()
        if settings.amplitude_track_events
        else MockAmplitudeClient()
    )


async def track_amplitude_event(
    user_id: int,
    event_type: str,
    event_properties: Properties | None = None,
    user_properties: Properties | None = None,
) -> None:
    await _track_event_in_amplitude(
        user_id, event_type, event_properties, user_properties
    )


async def _track_event_in_amplitude(
    user_id: int,
    event_type: str,
    event_properties: Properties | None = None,
    user_properties: Properties | None = None,
) -> None:
    amplitude_client = get_amplitude_client()
    event = BaseEvent(
        event_type=event_type,
        user_id=str(user_id),
        event_properties=event_properties,
        user_properties=user_properties,
    )
    amplitude_client.track(event)
    logger.info(
        f"Amplitude event tracked for user {user_id}: {event_type} with event properties {event_properties} and user properties {user_properties}"
    )


def register_endpoint_event(
    method: str,
    url_name: str,
    user_props_handler: PropsHandler | None = None,
    event_props_handler: PropsHandler | None = None,
) -> None:
    """
    Register a FastAPI endpoint as an Amplitude event.

    Args:
        method: HTTP method (GET, POST, etc.)
        url_name: Name of the endpoint route
        user_props_handler: Optional function to extract user properties
        event_props_handler: Optional function to extract event properties
    """
    event_name = f"{method} {url_name}"
    # Store the event info in registry
    if event_name not in event_name_to_info:
        event_name_to_info[event_name] = {
            "user_props_handler": user_props_handler,
            "event_props_handler": event_props_handler,
        }
    else:
        if user_props_handler:
            event_name_to_info[event_name]["user_props_handler"] = user_props_handler
        if event_props_handler:
            event_name_to_info[event_name]["event_props_handler"] = event_props_handler


async def track_amplitude_endpoint_event(
    request: Request,
    response: Response,
) -> None:
    """
    Track an Amplitude event based on the request and response.
    prepare_request_body must be called before this function to save the original request body.

    Args:
        request: The FastAPI request object
        response: The FastAPI response object
    """
    # Determine the user ID
    user_id: int | None = None
    is_authenticated = False

    if hasattr(request.state, "user"):
        user = request.state.user
        if user and hasattr(user, "id"):
            user_id = user.id
            is_authenticated = True

    # Try to get event from the registry
    endpoint = request.scope.get("endpoint", None)
    func_name = endpoint.__name__ if endpoint else None
    if not func_name:
        return

    event_name = f"{request.method} {func_name}"
    handler_info = event_name_to_info.get(event_name, None)

    # Only track events for authenticated users or allowed anonymous events
    if not is_authenticated and event_name not in ANONYMOUS_EVENT_TYPES:
        return

    # Parse request and response data
    try:
        request_data = {}
        if hasattr(request.state, "original_body"):
            request_data = json.loads(request.state.original_body)
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        request_data = {}

    try:
        response_data = {}
        if hasattr(response, "body"):
            response_data = json.loads(response.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        response_data = {}

    if not user_id and event_name in ANONYMOUS_EVENT_TYPES:
        try:
            user_id = response_data["id"]
        except KeyError:
            pass

    if not isinstance(user_id, int):
        return

    # Get user properties
    user_properties: Properties = {}
    if handler_info and handler_info["user_props_handler"]:
        # Use the registered handler
        user_properties = handler_info["user_props_handler"](
            request, request_data, response_data
        )

    # Get event properties
    event_properties: Properties = {}
    if handler_info and handler_info["event_props_handler"]:
        # Use the registered handler
        event_properties = handler_info["event_props_handler"](
            request, request_data, response_data
        )

    # Track the event
    await track_amplitude_event(
        user_id,
        event_name,
        user_properties=user_properties,
        event_properties=event_properties,
    )


async def prepare_request_body(request: Request) -> None:
    """Safely store the request body for later processing."""
    content_length = request.headers.get("content-length")
    content_type = request.headers.get("content-type", "")

    if content_length:
        try:
            content_length_int = int(content_length)
        except ValueError:
            content_length_int = None

        # Only process JSON content below the size threshold
        if (
            content_length_int
            and content_length_int < MAX_BODY_SIZE
            and "application/json" in content_type
        ):
            body = await request.body()
            # Store original body in request state
            request.state.original_body = body
            # Reset the request body so it can be read again
            request._body = body


register_endpoint_event(
    "POST",
    "fcm_device_create",
    user_props_handler=lambda request, request_data, response_data: {
        "device_type": response_data.get("type"),
    },
)

register_endpoint_event(
    "POST",
    "user_create",
    user_props_handler=lambda request, request_data, response_data: {
        "school": response_data.get("school"),
        "chosen_college": response_data.get("chosen_college"),
        "chosen_course": response_data.get("chosen_course"),
        "commitment": response_data.get("commitment"),
        "education_level": response_data.get("education_level"),
    },
)

register_endpoint_event(
    "PATCH",
    "user_set_commitment",
    user_props_handler=lambda request, request_data, response_data: {
        "commitment": request_data.get("commitment"),
    },
)

register_endpoint_event(
    "PATCH",
    "user_set_chosen_college",
    user_props_handler=lambda request, request_data, response_data: {
        "chosen_college": request_data.get("new_chosen_college"),
    },
)

register_endpoint_event(
    "PATCH",
    "user_set_chosen_course",
    user_props_handler=lambda request, request_data, response_data: {
        "chosen_course": request_data.get("new_chosen_course"),
    },
)

register_endpoint_event(
    "POST",
    "duel_list",
    event_props_handler=lambda request, request_data, response_data: {
        "duel_id": response_data.get("id"),
        "attacked_user_id": request_data.get("user_id"),
        "selection_method": request_data.get("selection_method"),
        "is_fast": request_data.get("is_fast"),
        "tournament_id": request_data.get("tournament_id"),
    },
)

register_endpoint_event(
    "PATCH",
    "duel_invite",
    event_props_handler=lambda request, request_data, response_data: {
        "invited_user_id": request_data.get("user_id"),
        "duel_id": int(request.path_params.get("id"))
        if "id" in request.path_params
        else None,
    },
)
