import logging
import logging.config
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable

import uvicorn
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.openapi.docs import (
    get_swagger_ui_html,
)
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Route
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import app.arq_client as arq_client
from app.admin_registry import admin_views, authentication_backend, require_admin_login
from app.community.routers import router as community_router
from app.config import Environment, settings
from app.database import db_manager
from app.deps import CurrentUserDep
from app.education.routers import router as education_router
from app.fcm.routers import router as fcm_router
from app.files.routers import router as files_router
from app.firebase_config import init_firebase
from app.flows.routers import areas_router, exam_router, flows_router
from app.logging_config import get_logging_config
from app.notifications.routers import router as in_app_notifications_router
from app.redis_client import use_redis
from app.shared.admin import AdminWithImport
from app.users.routers import token_router, user_router
from app.ws.routers import router as websockets_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.config.dictConfig(get_logging_config())
    init_firebase()

    async with db_manager.use_db(settings.database_url):
        async with use_redis():
            async with arq_client.arq_redis():
                admin = AdminWithImport(
                    app,
                    engine=db_manager.engine,
                    authentication_backend=authentication_backend,
                    base_url="/" + settings.admin_url,
                    debug=settings.environment in [Environment.DEV, Environment.TEST],
                )
                import_routes: list[Route] = [
                    Route(
                        "/{identity}/import",
                        endpoint=admin.import_csv,
                        name="import_csv",
                        methods=["GET", "POST"],
                    ),
                    Route(
                        "/{identity}/import/template",
                        endpoint=admin.import_template,
                        name="import_template",
                        methods=["GET"],
                    ),
                ]

                # Insert import routes before the existing routes
                admin.admin.router.routes = import_routes + admin.admin.router.routes

                for view in admin_views:
                    admin.add_view(view)

                yield


fastapi_app = FastAPI(
    lifespan=lifespan,
    openapi_url=None,
    docs_url=None,
)


# middlewares


fastapi_app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")


fastapi_app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    https_only=settings.environment == Environment.PROD,
)


# @fastapi_app.middleware("http")
# async def analytics_middleware(
#     request: Request, call_next: Callable[[Request], Awaitable[Response]]
# ):
#     response = await call_next(request)
#     try:
#         if (
#             response.status_code >= 200
#             and response.status_code < 300
#             and request.url.path.startswith("/api/")
#         ):
#             await track_amplitude_endpoint_event(request, response)
#     except Exception as e:
#         logger.error(f"Error tracking amplitude event: {e}")
#     finally:
#         return response


@fastapi_app.middleware("http")
async def logging_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
):
    start_time = time.monotonic()
    logger.info(f"Request started: {request.method} {request.url}")

    response = await call_next(request)

    duration = time.monotonic() - start_time

    logger.info(
        f"{request.method} {request.url} {response.status_code} - {duration:.6f}s total"
    )
    return response


@fastapi_app.middleware("http")
async def health_check_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
):
    if request.url.path == "/health":
        return Response(content="Healthy")
    return await call_next(request)


@fastapi_app.get(
    settings.docs_url,
    tags=["documentation"],
    include_in_schema=False,
    dependencies=[Depends(require_admin_login)],
)
async def docs() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url=f"{settings.openapi_url}?openapi_api_key={settings.openapi_api_key}",
        title="docs",
    )


@fastapi_app.get(
    settings.openapi_url,
    tags=["documentation"],
    include_in_schema=False,
)
async def openapi(request: Request) -> dict[str, Any]:
    return get_openapi(title="FastAPI", version="0.1.0", routes=fastapi_app.routes)


# have to do this weird thing instead of using /api as base_url of FastAPI() because sqladmin hardcoded admin urls without /api
base_api_router = APIRouter(prefix="/api")

# not authenticated (unless some authentication is required inside the router)
# if any route inside needs to have no authentication, add it to this router
base_api_router.include_router(token_router)
base_api_router.include_router(user_router)
base_api_router.include_router(websockets_router)
base_api_router.include_router(education_router)

# authenticated (all routes inside will have authentication)
authenticated_routers = APIRouter(dependencies=[CurrentUserDep])

authenticated_routers.include_router(community_router)
authenticated_routers.include_router(files_router)
authenticated_routers.include_router(flows_router)
authenticated_routers.include_router(exam_router)
authenticated_routers.include_router(areas_router)
authenticated_routers.include_router(in_app_notifications_router)
authenticated_routers.include_router(fcm_router)

# including base routers
base_api_router.include_router(authenticated_routers)
fastapi_app.include_router(base_api_router)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:fastapi_app",
        host=settings.uvicorn_host,
        port=settings.uvicorn_port,
        reload=settings.uvicorn_reload,
        loop="uvloop",
    )
