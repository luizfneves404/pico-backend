from typing import Any
from urllib.parse import urlencode

from api.controllers.chatrooms import (
    chatrooms_router,
    chatrooms_with_icon_router,
    dm_chatrooms_router,
)
from api.controllers.fcm_devices import router as fcm_devices_router
from api.controllers.files import router as files_groups_router
from api.controllers.messages import router as messages_router
from api.controllers.misc import router as misc_router
from api.controllers.schools import router as schools_router
from api.controllers.users import router as users_router
from challenges.api import tournaments_router
from currency.controllers.currency import router as currency_router
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from essays.controllers.essays import router as essay_topics_router
from ninja import NinjaAPI
from ninja.openapi.docs import Swagger
from ninja.throttling import AnonRateThrottle, AuthRateThrottle
from quiz.controllers.challenges import challenge_router
from quiz.controllers.duels import duel_router
from quiz.controllers.questions import router as questions_router
from quiz.controllers.quiz import answers_router, quiz_router
from study_plans.controllers.study_plan import router as study_plan_router

from pico_backend.auth import AsyncJWTBearer
from pico_backend.auth import router as token_router

swagger_settings = Swagger.default_settings
if settings.DEBUG:
    swagger_settings["persistAuthorization"] = True


class CustomDocs(Swagger):
    def get_openapi_url(self, api: "NinjaAPI", query_params: dict[str, Any]) -> str:
        base_url = reverse(f"{api.urls_namespace}:openapi-json")
        query_string = urlencode(query_params)
        full_url = f"{base_url}?{query_string}"
        return full_url

    def render_page(
        self, request: HttpRequest, api: NinjaAPI, **kwargs: Any
    ) -> HttpResponse:
        kwargs["openapi_api_key"] = settings.OPENAPI_API_KEY
        return super().render_page(request, api, **kwargs)


api = NinjaAPI(
    urls_namespace="api",
    docs_decorator=staff_member_required,
    docs_url=settings.DOCS_URL,
    openapi_url=settings.OPENAPI_URL,
    docs=CustomDocs(),
    auth=AsyncJWTBearer(),
    throttle=[
        AnonRateThrottle("2000/d"),
        AuthRateThrottle("15000/d"),
    ],
)

# Add all routers
api.add_router("/token", token_router, tags=["token"])
api.add_router("/users", users_router, tags=["users"])
api.add_router("/schools", schools_router, tags=["schools"])
api.add_router("/chatrooms", chatrooms_router, tags=["chatrooms"])
api.add_router(
    "/chatrooms-with-icon", chatrooms_with_icon_router, tags=["chatrooms-with-icon"]
)
api.add_router("/dm-chatrooms", dm_chatrooms_router, tags=["dm-chatrooms"])
api.add_router("", messages_router, tags=["messages"])
api.add_router("", misc_router, tags=["misc"])
api.add_router("/devices", fcm_devices_router, tags=["devices"])
api.add_router("", files_groups_router, tags=["files-groups"])
api.add_router("/essay-topics", essay_topics_router, tags=["essay-topics"])
api.add_router("/quiz", quiz_router, tags=["quiz"])
api.add_router("/answers", answers_router, tags=["answers"])
api.add_router("/questions", questions_router, tags=["questions"])
api.add_router("/study-plan", study_plan_router, tags=["study-plan"])
api.add_router("/duels", duel_router, tags=["duels"])
api.add_router("/currency", currency_router, tags=["currency"])
api.add_router("/new-challenges", challenge_router, tags=["new-challenges"])
api.add_router("/tournaments", tournaments_router, tags=["tournaments"])
