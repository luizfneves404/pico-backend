import logging
from typing import Annotated, Any, Literal

import api.services.user_service as user_service
from api.models import User
from api.models.user import EducationLevel
from api.schemas.users import (
    BalanceOut,
    CommitmentIn,
    CurrentPasswordIn,
    EducationLevelIn,
    EmailIn,
    NewChosenCollegeIn,
    NewChosenCourseIn,
    NewSchoolIn,
    OnlineInfo,
    OtherUserOut,
    PhoneNumber,
    PhoneNumberIn,
    RawPhoneNumbersIn,
    ReferredByIn,
    UserIdsIn,
    UserIn,
    UserInRanking,
    UserMeStatsOut,
    UsernameIn,
    UserOut,
    UserStatsOut,
)
from django.contrib.auth.tokens import default_token_generator
from django.db.models import QuerySet
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from ninja import Body, Field, Schema
from ninja.conf import settings
from ninja.errors import HttpError
from ninja.pagination import PageNumberPagination, paginate
from ninja.router import Router
from shared.validation import LowercaseEmailStr

logger = logging.getLogger(__name__)

router = Router()


class FlexiblePageNumberPagination(PageNumberPagination):
    items_attribute: str = "results"

    class Output(Schema):
        results: list[Any]
        count: int

    class Input(Schema):
        page: int = Field(1, ge=1)
        page_size: int = Field(
            settings.PAGINATION_PER_PAGE,
            ge=1,
        )

    def paginate_queryset(
        self,
        queryset: QuerySet,
        pagination: Input,
        **params: Any,
    ) -> Any:
        offset = (pagination.page - 1) * pagination.page_size
        return {
            "results": queryset[offset : offset + pagination.page_size],
            "count": self._items_count(queryset),
        }

    async def apaginate_queryset(
        self,
        queryset: QuerySet,
        pagination: Input,
        **params: Any,
    ) -> Any:
        offset = (pagination.page - 1) * pagination.page_size
        return {
            "results": queryset[offset : offset + pagination.page_size],
            "count": await self._aitems_count(queryset),
        }


@router.post(
    "/request-password-reset",
    response={200: None},
    auth=None,
    url_name="user_request_password_reset",
)
async def user_request_password_reset(request, email_in: EmailIn):
    try:
        logger.info(
            f"User {email_in.email.split('@')[0][:3]}***@{email_in.email.split('@')[1]} requested password reset"
        )
        user = await User.non_sentinel_objects.aget(email=email_in.email)
        logger.info(f"User {user.id} requested password reset")
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.id))
        password_reset_url = request.build_absolute_uri(
            reverse("password_reset_confirm", args=[uid, token])
        )
        context = {
            "user": user,
            "password_reset_url": password_reset_url,
        }
        email_subject = "Password Reset Requested"
        email_body = render_to_string("api/password_reset_email.html", context)
        user_service.send_html_email(
            email_subject,
            email_body,
            user.email,
        )
        return 200, None
    except User.DoesNotExist:
        raise HttpError(404, "No user found with this email")
    except User.MultipleObjectsReturned:
        raise HttpError(400, "More than one user found with this email")


@router.post("", response={201: UserOut}, auth=None, url_name="user_create")
async def user_create(request, user_in: UserIn):
    try:
        new_user = await user_service.create_user(
            user_in.username.strip(),
            user_in.password,
            user_in.phone_number,
            user_in.email,
            chosen_college=user_in.chosen_college,
            chosen_course=user_in.chosen_course,
            education_level=user_in.education_level,
            signup_source=user_in.signup_source,
            referred_by_username=user_in.referred_by_username,
            commitment=user_in.commitment,
            school=user_in.school,
            school_id=user_in.school_id,
        )
    except user_service.UsernameTakenError:
        raise HttpError(409, "Username already taken, maybe with different case")
    except user_service.PhoneNumberTakenError:
        raise HttpError(409, "Phone number already taken")
    except user_service.EmailTakenError:
        raise HttpError(409, "Email already taken")
    except user_service.ReferredByNotFoundError:
        raise HttpError(404, "Referred by user not found")
    else:
        return 201, UserOut.model_validate(
            (await user_service.ato_user_out([new_user.id]))[0]
        )


@router.get("/me", response=UserOut, url_name="user_me")
async def user_me(request):
    user = request.auth
    return UserOut.model_validate((await user_service.ato_user_out([user.id]))[0])


@router.delete("/me", response={204: None}, url_name="user_me")
async def user_destroy(request, current_password_schema: CurrentPasswordIn):
    user = request.auth
    current_password = current_password_schema.current_password
    try:
        await user_service.delete_user(user, current_password)
    except user_service.InvalidCredentialsError:
        raise HttpError(401, "Incorrect password")


@router.post(
    "/validate-username",
    response={200: None},
    url_name="user_validate_username",
    auth=None,
)
async def user_validate_username(request, username_in: UsernameIn):
    try:
        await user_service.validate_username(username_in.username.strip())
    except user_service.UsernameTakenError:
        raise HttpError(409, "Username already taken")
    return 200, None


@router.post(
    "/validate-phone-number",
    response={200: None},
    url_name="user_validate_phone_number",
    auth=None,
)
async def user_validate_phone_number(request, phone_number_in: PhoneNumberIn):
    try:
        await user_service.validate_phone_number(phone_number_in.phone_number)
    except user_service.PhoneNumberTakenError:
        raise HttpError(409, "Phone number already taken")
    return 200, None


@router.post(
    "/validate-email",
    response={200: None},
    url_name="user_validate_email",
    auth=None,
)
async def user_validate_email(request, email_in: EmailIn):
    try:
        await user_service.validate_email(email_in.email)
    except user_service.EmailTakenError:
        raise HttpError(409, "Email already taken")
    return 200, None


@router.patch(
    "/set-username",
    response={204: None},
    url_name="user_set_username",
)
async def user_set_username(
    request,
    new_username: Annotated[str, Body()],
    current_password: Annotated[str, Body()],
):
    user = request.auth
    try:
        await user_service.set_username(user, new_username.strip(), current_password)
    except user_service.UsernameTakenError:
        raise HttpError(
            409, "User with this username already exists, maybe with different case"
        )
    except user_service.InvalidCredentialsError:
        raise HttpError(401, "Incorrect password")


@router.patch(
    "/set-password",
    response={204: None},
    url_name="user_set_password",
)
async def user_set_password(
    request,
    new_password: Annotated[str, Body()],
    current_password: Annotated[str, Body()],
):
    user = request.auth
    try:
        await user_service.set_password(user, new_password, current_password)
    except user_service.InvalidCredentialsError:
        raise HttpError(401, "Incorrect password")


@router.patch(
    "/set-phone-number",
    response={204: None},
    url_name="user_set_phone_number",
)
async def user_set_phone_number(
    request,
    new_phone_number: Annotated[PhoneNumber, Body()],
    current_password: Annotated[str, Body()],
):
    user = request.auth
    try:
        await user_service.set_phone_number(user, new_phone_number, current_password)
    except user_service.PhoneNumberTakenError:
        raise HttpError(409, "Phone number already taken")
    except user_service.InvalidCredentialsError:
        raise HttpError(401, "Incorrect password")


@router.patch(
    "/set-email",
    response={204: None},
    url_name="user_set_email",
)
async def user_set_email(
    request,
    new_email: Annotated[LowercaseEmailStr, Body()],
    current_password: Annotated[str, Body()],
):
    user = request.auth
    try:
        await user_service.set_email(user, new_email, current_password)
    except user_service.EmailTakenError:
        raise HttpError(409, "Email already taken")
    except user_service.InvalidCredentialsError:
        raise HttpError(401, "Incorrect password")


@router.patch(
    "/set-school",
    response={204: None},
    url_name="user_set_school",
)
async def user_set_school(request, new_school_in: NewSchoolIn):
    user = request.auth
    try:
        await user_service.set_school(
            user, new_school_in.new_school, new_school_in.new_school_id
        )
    except user_service.InvalidCredentialsError:
        raise HttpError(401, "Incorrect password")


@router.patch(
    "/set-chosen-college",
    response={204: None},
    url_name="user_set_chosen_college",
)
async def user_set_chosen_college(request, new_chosen_college: NewChosenCollegeIn):
    user = request.auth
    await user_service.set_chosen_college(user, new_chosen_college.new_chosen_college)


@router.patch(
    "/set-chosen-course",
    response={204: None},
    url_name="user_set_chosen_course",
)
async def user_set_chosen_course(request, new_chosen_course: NewChosenCourseIn):
    user = request.auth
    await user_service.set_chosen_course(user, new_chosen_course.new_chosen_course)


@router.patch(
    "/set-education-level",
    response={204: None},
    url_name="user_set_education_level",
)
async def user_set_education_level(request, education_level_in: EducationLevelIn):
    user = request.auth
    await user_service.set_education_level(user, education_level_in.education_level)


@router.patch(
    "/set-referred-by",
    response={204: None},
    url_name="user_set_referred_by",
)
async def user_set_referred_by(request, referred_by_in: ReferredByIn):
    user = request.auth
    try:
        await user_service.set_referred_by(
            user, referred_by_in.new_referred_by_username
        )
    except user_service.ReferredByNotFoundError:
        raise HttpError(404, "Referred by user not found")


@router.patch(
    "/set-commitment",
    response={204: None},
    url_name="user_set_commitment",
)
async def user_set_commitment(request, commitment_in: CommitmentIn):
    user = request.auth
    await user_service.set_commitment(user, commitment_in.commitment)


@router.post(
    "/check-contacts",
    response={200: list[OtherUserOut]},
    url_name="check_contacts",
)
@paginate(FlexiblePageNumberPagination)
async def check_contacts(request, raw_phone_numbers_schema: RawPhoneNumbersIn):
    raw_phone_numbers = raw_phone_numbers_schema.phone_numbers
    users = await user_service.check_contacts(raw_phone_numbers)
    user_outs = await user_service.to_other_user_out([user.id for user in users])
    return user_outs


@router.get(
    "/search-username",
    response={200: list[OtherUserOut]},
    url_name="search_username",
    auth=None,
)
@paginate(FlexiblePageNumberPagination)
async def search_username(request, username: str):
    users = await user_service.search_username(username)
    user_outs = await user_service.to_other_user_out([user.id for user in users])
    return user_outs


@router.get(
    "/sentinel",
    response={200: list[OtherUserOut]},
    url_name="sentinel_users",
)
async def sentinel_users(request):
    users = await User.objects.aget_sentinel_users()
    user_outs = await user_service.to_other_user_out([user.id for user in users])
    return user_outs


@router.get(
    "/stats",
    response={200: UserMeStatsOut},
    url_name="user_stats_me",
)
async def user_stats_me(request):
    return await user_service.get_user_stats_from_id(request.auth.id)


@router.get(
    "/{username}/stats",
    response={200: UserStatsOut},
    url_name="user_stats",
)
async def user_stats(request, username: str):
    try:
        return await user_service.get_user_stats_from_username(username)
    except user_service.UserNotFoundError:
        raise HttpError(404, "User not found")


@router.get(
    "/ranking",
    response={200: list[UserInRanking]},
    url_name="user_ranking",
)
async def user_ranking(
    request,
    school_filter: int | None = None,
    course_filter: str | None = None,
    score_type: Literal["dynamic", "percentage"] = "dynamic",
    education_level_filter: EducationLevel | None = None,
    subject: str | None = None,
):
    if score_type == "dynamic" and subject is not None:
        raise HttpError(400, "Subject is not allowed for dynamic score type")
    user = request.auth
    return await user_service.get_ranking(
        user.id,
        score_type=score_type,
        school_filter=school_filter,
        course_filter=course_filter,
        education_level_filter=education_level_filter,
        subject=subject,
    )


@router.post(
    "/online-info",
    response={200: list[OnlineInfo]},
    url_name="user_online_info",
)
async def get_online_info(request, user_ids_in: UserIdsIn):
    return await user_service.get_online_info(user_ids_in.user_ids)


@router.get(
    "/me/balance",
    response={200: BalanceOut},
    url_name="get_balance",
)
async def get_balance(request):
    try:
        return {"balance": await user_service.get_balance(request.auth.id)}
    except user_service.UserNotFoundError:
        raise HttpError(404, "User not found")
