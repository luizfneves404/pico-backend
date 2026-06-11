import logging
from datetime import datetime, timedelta
from typing import Any, Literal

import api.services.chatroom_service as chatroom_service
import chat.chat_service as chat_service
import currency.currency_service as currency_service
import notifications.utils as notification_utils
import quiz.quiz_service as quiz_service
from api.models import (
    Chatroom,
    College,
    Course,
    EducationLevel,
    School,
    SignupSource,
    User,
)
from api.schemas.users import PhoneNumber
from api.services import fcm_service
from asgiref.sync import sync_to_async
from celery import shared_task
from currency.models import Currency, CurrencyAction, CurrencyType
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.db.utils import IntegrityError
from django.utils import timezone
from django.utils.html import strip_tags
from pydantic import TypeAdapter, ValidationError
from quiz.models import SessionQuestionUser, UserInfo

import pico_backend.amp as pico_backend_amp

# Constants
from .constants import (
    NUM_RANKED_USERS,
    STARTING_DUEL_SCORE,
    WELCOME_EMAIL_MESSAGE,
    WELCOME_EMAIL_SUBJECT,
    YOU_AND_PICO_CHATROOM_MESSAGES,
    YOU_AND_PICO_CHATROOM_NAME,
)

logger = logging.getLogger(__name__)

phone_number_adapter = TypeAdapter(PhoneNumber)


# Exceptions
class UserServiceError(Exception):
    """Base exception for user service errors."""


class PhoneNumberTakenError(UserServiceError):
    """Exception raised when a phone number is already taken."""


class EmailTakenError(UserServiceError):
    """Exception raised when an email is already taken."""


class UsernameTakenError(UserServiceError):
    """Exception raised when a username is already taken."""


class InvalidCredentialsError(UserServiceError):
    """Exception raised for invalid user credentials."""


class UserNotFoundError(UserServiceError):
    """Exception raised when a user is not found."""


class ReferredByNotFoundError(UserServiceError):
    """Exception raised when a referred by user is not found."""


def to_user_out(user_ids: list[int]):
    users = (
        User.objects.filter(id__in=user_ids)
        .select_related("chosen_college", "chosen_course", "school")
        .with_referral_count()
    )
    user_dict = {user.id: user for user in users}
    return [
        {
            "id": user_id,
            "username": user_dict[user_id].username,
            "phone_number": user_dict[user_id].phone_number,
            "email": user_dict[user_id].email,
            "school": user_dict[user_id].school.name
            if user_dict[user_id].school
            else "",
            "school_id": user_dict[user_id].school_id,
            "chosen_college": (
                user_dict[user_id].chosen_college.name
                if user_dict[user_id].chosen_college
                else ""
            ),
            "chosen_course": (
                user_dict[user_id].chosen_course.name
                if user_dict[user_id].chosen_course
                else ""
            ),
            "education_level": user_dict[user_id].education_level,
            "referral_count": user_dict[user_id].referral_count,
            "commitment": user_dict[user_id].commitment,
            "balance": user_dict[user_id].balance,
            "signup_source": user_dict[user_id].signup_source,
        }
        for user_id in user_ids
        if user_id in user_dict
    ]


async def ato_user_out(user_ids: list[int]) -> list[dict]:
    return await sync_to_async(to_user_out)(user_ids)


async def to_other_user_out(user_ids: list[int]) -> list[dict]:
    users = User.objects.filter(id__in=user_ids).select_related("school")
    return [
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "phone_number": user.phone_number,
            "school": user.school.name if user.school else "",
            "school_id": user.school_id,
        }
        async for user in users
    ]


# Helper functions
async def _get_or_create_college_course(
    chosen_college: str | None, chosen_course: str | None
) -> tuple[College | None, Course | None]:
    college = None
    course = None

    if chosen_college:
        college, _ = await College.objects.aget_or_create(
            name=chosen_college,
            defaults={"user_submitted": True},
        )

    if chosen_course:
        course, _ = await Course.objects.aget_or_create(
            name=chosen_course,
            defaults={"user_submitted": True},
        )

    if college and course:
        await college.courses.aadd(course)

    return college, course


# Main functions
async def create_user(
    username: str,
    password: str,
    phone_number: str,
    email: str,
    chosen_college: str,
    chosen_course: str,
    education_level: EducationLevel,
    signup_source: SignupSource,
    referred_by_username: str,
    commitment: int,
    school: str = "",  # deprecated
    school_id: int | None = None,
) -> User:
    college, course = await _get_or_create_college_course(chosen_college, chosen_course)
    if referred_by_username:
        referred_by = await User.non_sentinel_objects.filter(
            username=referred_by_username
        ).afirst()
        if not referred_by:
            raise ReferredByNotFoundError
    else:
        referred_by = None

    if await User.objects.filter(username__iexact=username).aexists():
        raise UsernameTakenError

    if school:
        school_obj, _ = await School.objects.aget_or_create(
            name=school, defaults={"user_submitted": True}
        )
    else:
        school_obj = None
    try:
        new_user = await User.objects.acreate_user(
            username=username,
            password=password,
            phone_number=phone_number,
            email=email,
            school_id=school_id if school_id else school_obj.id if school_obj else None,
            chosen_college=college,
            chosen_course=course,
            referred_by=referred_by,
            commitment=commitment,
            education_level=education_level,
            signup_source=signup_source,
        )
    except IntegrityError as e:
        error_message = str(e)
        if "phone_number" in error_message:
            raise PhoneNumberTakenError
        elif "email" in error_message:
            raise EmailTakenError
        else:
            raise UserServiceError(error_message)

    logger.info(f"Created user {new_user.username}")

    await UserInfo.objects.acreate(user=new_user, duel_score=STARTING_DUEL_SCORE)

    send_welcome_email(new_user)

    if referred_by:
        await sync_to_async(reward_referral)(referred_by, new_user)

    return new_user


def reward_referral(referred_by: User, new_user: User) -> None:
    currency_service.handle_currency_transaction(
        user=referred_by,
        action=CurrencyAction.USER_REFERRED_ANOTHER,
        transaction_type=CurrencyType.REWARD,
        related_object=new_user,
    )
    currency_service.handle_currency_transaction(
        user=new_user,
        action=CurrencyAction.ANOTHER_USER_REFERRED_ME,
        transaction_type=CurrencyType.REWARD,
        related_object=referred_by,
    )
    try:
        value = Currency.get_default(
            CurrencyAction.USER_REFERRED_ANOTHER, CurrencyType.REWARD
        ).value
    except Currency.DoesNotExist:
        logger.warning(
            f"No default currency found for action {CurrencyAction.USER_REFERRED_ANOTHER} and currency type {CurrencyType.REWARD}"
        )
        return

    fcm_service.send_notification(
        new_user.id,
        f"{referred_by.username} te recomendou o Pico!",
        f"{referred_by.username} recomendou o Pico para você! Você receberá {value} moedas por isso. Já estão disponíveis na sua conta!",
    )
    fcm_service.send_notification(
        referred_by.id,
        f"{new_user.username} se cadastrou usando sua referência!",
        f"Você recebeu {value} moedas por ter recomendado o Pico para {new_user.username}. Já estão disponíveis na sua conta!",
    )


async def validate_username(username: str) -> None:
    if await User.objects.filter(username__iexact=username).aexists():
        raise UsernameTakenError


async def validate_phone_number(phone_number: str) -> None:
    if await User.objects.filter(phone_number=phone_number).aexists():
        raise PhoneNumberTakenError


async def validate_email(email: str) -> None:
    if await User.objects.filter(email__iexact=email).aexists():
        raise EmailTakenError


async def set_username(user: User, new_username: str, current_password: str) -> None:
    if not user.check_password(current_password):
        raise InvalidCredentialsError
    if await User.objects.filter(username__iexact=new_username).aexists():
        raise UsernameTakenError
    user.username = new_username
    await user.asave()
    logger.info(f"User {user.id} changed their username to {new_username}")


async def set_password(user: User, new_password: str, current_password: str) -> None:
    if not user.check_password(current_password):
        raise InvalidCredentialsError
    user.set_password(new_password)
    await user.asave()
    logger.info(f"User {user.id} changed their password")


async def set_phone_number(
    user: User, new_phone_number: str, current_password: str
) -> None:
    if not user.check_password(current_password):
        raise InvalidCredentialsError
    if await User.objects.filter(phone_number=new_phone_number).aexists():
        raise PhoneNumberTakenError
    user.phone_number = new_phone_number
    await user.asave()
    logger.info(f"User {user.id} changed their phone number to {new_phone_number}")


async def set_email(user: User, new_email: str, current_password: str) -> None:
    if not user.check_password(current_password):
        raise InvalidCredentialsError
    if await User.objects.filter(email__iexact=new_email).aexists():
        raise EmailTakenError
    user.email = new_email
    await user.asave()
    logger.info(f"User {user.id} changed their email")


async def set_school(
    user: User, new_school: str = "", new_school_id: int | None = None
) -> None:
    if new_school:
        school_obj, _ = await School.objects.aget_or_create(
            name=new_school, defaults={"user_submitted": True}
        )
    else:
        school_obj = None
    user.school_id = (
        new_school_id if new_school_id else school_obj.id if school_obj else None
    )

    await user.asave()
    logger.info(
        f"User {user.id} changed their school to {new_school} or {new_school_id}"
    )


async def set_chosen_college(user: User, new_chosen_college: str) -> None:
    refetched_user = await User.objects.select_related("chosen_course").aget(id=user.id)
    college, _ = await _get_or_create_college_course(
        new_chosen_college,
        refetched_user.chosen_course.name if refetched_user.chosen_course else None,
    )
    user.chosen_college = college
    await user.asave()
    logger.info(
        f"User {user.id} changed their chosen college to '{new_chosen_college}'"
    )


async def set_chosen_course(user: User, new_chosen_course: str) -> None:
    refetched_user = await User.objects.select_related("chosen_college").aget(
        id=user.id
    )
    _, course = await _get_or_create_college_course(
        refetched_user.chosen_college.name if refetched_user.chosen_college else None,
        new_chosen_course,
    )
    user.chosen_course = course
    await user.asave()
    logger.info(f"User {user.id} changed their chosen course to '{new_chosen_course}'")


async def set_education_level(user: User, new_education_level: str) -> None:
    user.education_level = new_education_level
    await user.asave()
    logger.info(
        f"User {user.id} changed their education level to '{new_education_level}'"
    )


async def set_referred_by(user: User, new_referred_by_username: str) -> None:
    new_referred_by = await User.non_sentinel_objects.filter(
        username=new_referred_by_username
    ).afirst()
    if not new_referred_by:
        raise ReferredByNotFoundError
    user.referred_by = new_referred_by
    await user.asave()
    logger.info(
        f"User {user.id} changed their referred by to '{new_referred_by_username}'"
    )


async def set_commitment(user: User, commitment: int) -> None:
    user.commitment = commitment
    await user.asave()
    logger.info(f"User {user.id} changed their commitment to {commitment}")


async def delete_user(user: User, current_password: str) -> None:
    if not await user.acheck_password(current_password):
        raise InvalidCredentialsError
    logger.info(f"Deleting user {user.id}")
    pico_backend_amp.delete_user(user.id)
    await user.adelete()


async def check_contacts(raw_phone_numbers: list[str]) -> list[User]:
    phone_numbers = []
    for phone_number in raw_phone_numbers:
        try:
            phone_numbers.append(phone_number_adapter.validate_python(phone_number))
        except ValidationError:
            pass
    logger.debug(
        f"Contacts checked! There were {len(phone_numbers)} valid phone numbers"
    )
    matched_users = [
        user
        async for user in (
            User.non_sentinel_objects.filter(phone_number__in=phone_numbers).order_by(
                "username"
            )
        )
    ]
    logger.debug(f"Found {len(matched_users)} matching users after checking contacts")
    return matched_users


async def search_username(username: str) -> list[User]:
    logger.debug(f"Searching for username containing '{username}'")
    return [
        user
        async for user in User.non_sentinel_objects.filter(
            username__icontains=username
        ).order_by("username")
    ]


async def create_official_chatroom_for_user(user: User) -> Chatroom:
    messages = YOU_AND_PICO_CHATROOM_MESSAGES.copy()
    return await chatroom_service.create_predefined_chatroom_with_messages(
        YOU_AND_PICO_CHATROOM_NAME,
        user,
        [],
        messages,
    )


def send_welcome_email(user: User) -> None:
    send_mail(
        WELCOME_EMAIL_SUBJECT,
        WELCOME_EMAIL_MESSAGE.format(username=user.username),
        None,
        [user.email],
    )
    logger.info(f"Sent welcome email to '{user.username}'")


def send_bulk_email(
    users: list[User], subject: str, html_string: str, id_zero_padding: int = 0
) -> None:
    for user in users:
        # Replace template markers with user data
        personalized_html = (
            html_string.replace(
                "%%id%%",
                (
                    str(user.id).zfill(id_zero_padding)
                    if id_zero_padding
                    else str(user.id)
                ),
            )
            .replace("%%username%%", user.username)
            .replace("%%email%%", user.email)
        )
        task_send_html_email.delay(subject, personalized_html, user.email).forget()
    logger.info(f"Sent celery tasks to bulk email {len(users)} users")


def send_html_email(subject: str, html_string: str, email: str):
    send_mail(
        subject=subject,
        message=strip_tags(html_string),
        from_email=None,
        recipient_list=[email],
        html_message=html_string,
    )


@shared_task(rate_limit="5/s")
def task_send_html_email(subject: str, html_string: str, email: str):
    send_html_email(subject, html_string, email)


def get_streak_info(answer_timestamps: list[datetime]) -> tuple[bool, int]:
    """
    Receives a list of user answer timestamps.
    Returns a tuple of done_today and streak.
    """
    ordered_timestamps = sorted(answer_timestamps, reverse=True)

    streak = 0
    today = timezone.localdate()
    done_today = False
    last_processed_date = None
    for timestamp in ordered_timestamps:
        current_date = timezone.localdate(timestamp)
        if last_processed_date == current_date:
            continue
        last_processed_date = current_date

        if streak == 0:
            if current_date == today:
                done_today = True
                streak += 1
            elif current_date == today - timedelta(days=1):
                streak += 1
            else:
                break
        else:
            if current_date == today - timedelta(
                days=streak + 1 if not done_today else streak
            ):
                streak += 1
            else:
                break

    return done_today, streak


async def get_user_stats_from_username(username: str) -> dict:
    user = await User.objects.filter(username__iexact=username).afirst()
    if not user:
        raise UserNotFoundError
    return await get_user_stats(user)


async def get_user_stats_from_id(user_id: int) -> dict:
    user = await User.objects.aget(id=user_id)
    return await get_user_stats(user)


async def get_user_stats(user: User) -> dict:
    user_stats = await quiz_service.acalc_user_stats(user.id)

    user_out = (await ato_user_out([user.id]))[0]
    user_answers_timestamps = [
        answer["timestamp"]
        async for answer in SessionQuestionUser.objects.filter(
            Q(choice__isnull=False) | ~Q(submitted_text__exact=""),
            user_id=user.id,
        )
        .order_by("-timestamp")
        .values("timestamp")
    ]
    done_today, streak = get_streak_info(user_answers_timestamps)

    percentage_score = await sync_to_async(quiz_service.get_user_percentage_score)(
        user.id
    )

    user_info, _ = await UserInfo.objects.aget_or_create(
        user_id=user.id, defaults={"duel_score": STARTING_DUEL_SCORE}
    )

    user_stats.update(
        {
            "id": user.id,
            "username": user.username,
            "school": user_out["school"],
            "school_id": user_out["school_id"],
            "score": user_stats["score"],
            "area_expected_scores": {
                "Matemática": user_stats["area_expected_scores"]["Matemática"],
                "Linguagem": user_stats["area_expected_scores"][
                    "Linguagens"
                ],  # deveria ser Linguagens, mas o front ta esperando errado
                "Ciências Humanas": user_stats["area_expected_scores"][
                    "Ciências Humanas"
                ],
                "Ciências da Natureza": user_stats["area_expected_scores"][
                    "Ciências da Natureza"
                ],
            },
            "dynamic_score": user_info.dynamic_score,
            "percentage_score": percentage_score,
            "chosen_college": user_out["chosen_college"],
            "chosen_course": user_out["chosen_course"],
            "education_level": user_out["education_level"],
            "streak": streak,
            "done_today": done_today,
        }
    )
    return user_stats


async def get_ranking(
    asking_user_id: int,
    score_type: Literal["dynamic", "percentage"],
    school_filter: int | None,
    course_filter: str | None,
    education_level_filter: EducationLevel | None,
    subject: str | None = None,
) -> list[dict[str, Any]]:
    filters = {}
    if school_filter:
        filters["school_id"] = school_filter
    if course_filter:
        filters["chosen_course__name"] = course_filter
    if education_level_filter:
        filters["education_level"] = education_level_filter

    users_ids = [
        id
        async for id in User.non_sentinel_objects.filter(**filters).values_list(
            "id", flat=True
        )
    ]
    if score_type == "dynamic":
        return await sync_to_async(
            quiz_service.get_ranked_users_stats_by_dynamic_score
        )(users_ids, NUM_RANKED_USERS, asking_user_id)
    elif score_type == "percentage":
        return await sync_to_async(quiz_service.get_ranked_users_stats_by_percentage)(
            users_ids, NUM_RANKED_USERS, asking_user_id, subject
        )
    else:
        raise ValueError(f"Invalid score type: {score_type}")


def get_user_infos(users: list[User]) -> list[dict]:
    total_answers = (
        SessionQuestionUser.objects.filter(user__in=users)
        .values("user")
        .annotate(total_answers=Count("id"))
    )
    answer_dict = {item["user"]: item["total_answers"] for item in total_answers}

    return [
        {
            "username": user.username,
            "total_answers": answer_dict.get(user.id, 0),
            "date_joined": user.date_joined,
        }
        for user in users
    ]


async def get_online_info(user_ids: list[int]) -> list[dict]:
    """Get online status and last online time for a list of users.

    Args:
        user_ids: List of user IDs to check status for

    Returns:
        List of dicts containing:
            - id: user ID
            - is_online: boolean indicating if the user is online
            - last_online: last online time for offline users, None for online users
    """
    # Get current online/offline status for all users
    statuses = await notification_utils.aget_user_statuses(user_ids)

    # Get last online time for offline users
    offline_user_ids = [
        user_id for user_id, status in zip(user_ids, statuses) if status != "online"
    ]
    last_online_users = await sync_to_async(chat_service.get_last_online_users)(
        offline_user_ids
    )

    # Build response combining status and last online time
    return [
        {
            "id": user_id,
            "is_online": status == "online",  # Convert to boolean
            "last_online": last_online_users.get(user_id)
            if status != "online"
            else None,
        }
        for user_id, status in zip(user_ids, statuses)
    ]


async def get_balance(user_id: int) -> int:
    user = await User.objects.filter(id=user_id).values("balance").afirst()
    if not user:
        raise UserNotFoundError
    return user["balance"]
