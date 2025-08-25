from typing import Any, Sequence

import logfire
from fastapi import FastAPI, Request, WebSocket
from opentelemetry.context import Context
from opentelemetry.instrumentation.arq import ArqInstrumentor
from opentelemetry.sdk.trace.sampling import (
    Decision,
    ParentBased,
    Sampler,
    SamplingResult,
    TraceIdRatioBased,
)
from opentelemetry.trace import Link, SpanKind, TraceState
from opentelemetry.util.types import Attributes

from app.config import Environment, settings
from app.ws.routers import WEBSOCKET_URL

# This attribute key is standard for OpenTelemetry database instrumentations.
STATEMENT_KEY = "logfire.msg"


class ArqPollingSampler(Sampler):
    """
    A custom sampler that drops traces for arq's redis polling
    but keeps all other traces.
    """

    def __init__(self):
        # We'll use the default Logfire sampler as our fallback.
        # This traces everything but can be changed (e.g., to sample 50% of traces).
        self._fallback_sampler = ParentBased(TraceIdRatioBased(1.0))

    def get_description(self) -> str:
        return "A custom sampler that drops traces for arq's redis polling but keeps all other traces."

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes | None = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        # Check if the span has attributes and the db.statement key
        if attributes and STATEMENT_KEY in attributes:
            statement = attributes[STATEMENT_KEY]
            # arq has some internal operations that we can safely ignore.
            if isinstance(statement, str) and (
                statement.startswith("ZRANGEBYSCORE")
                or statement.startswith("PSETEX")
                or statement.startswith("ZCARD")
                or statement.startswith("ZSCORE")
                or statement.startswith("WATCH")
                or statement.startswith("EXISTS")
            ):
                # Tell OpenTelemetry to drop this span and not record it.
                return SamplingResult(decision=Decision.DROP)

        # For all other spans, defer to the default sampler's decision.
        return self._fallback_sampler.should_sample(
            parent_context, trace_id, name, kind, attributes, links
        )


def instrument_base() -> None:
    # logfire.instrument_sqlalchemy() # this should work, but I think there's a bug in logfire's sqlalchemy instrumentation
    # instead, we are instrumenting the engine in database.py
    logfire.instrument_redis()
    logfire.instrument_openai()


def request_attributes_mapper(
    request: Request | WebSocket, attributes: dict[str, Any]
) -> dict[str, Any]:
    """
    As per logfire docs:
    The request_attributes_mapper function mustn't mutate the contents of values or errors, but it can safely replace them with new values.
    """
    if attributes["errors"]:
        # Only log validation errors, not valid arguments
        return {
            # This will become the `fastapi.arguments.errors` attribute
            "errors": attributes["errors"],
        }
    else:
        # Don't log anything for valid requests
        return {}


def instrument_app(app: FastAPI) -> None:
    logfire.configure(
        environment=settings.environment,
        service_name="backend",
        distributed_tracing=False,
        console=None if settings.environment == Environment.DEV else False,
    )
    instrument_base()
    logfire.instrument_fastapi(
        app,
        capture_headers=True,
        excluded_urls=[settings.health_check_url, WEBSOCKET_URL],
        request_attributes_mapper=request_attributes_mapper,
    )
    ArqInstrumentor().instrument()


def instrument_worker() -> None:
    logfire.configure(
        environment=settings.environment,
        service_name="worker",
        sampling=logfire.SamplingOptions(head=ParentBased(ArqPollingSampler())),
        distributed_tracing=True,
    )
    instrument_base()
    ArqInstrumentor().instrument()
