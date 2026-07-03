"""Structured JSON logging with a request ID threaded through every line.

This satisfies the brief's observability requirement: tool call logs,
request/response traces, error logs, and basic latency tracking. A plain
`logging.Formatter` writing JSON to stdout is deliberately the whole
mechanism here -- this is the *required* observability item, not the
optional bonus (OpenTelemetry/LangSmith/Arize/a custom trace viewer is
proposed separately, only once everything required is done and approved).
JSON-to-stdout is exactly what "structured JSON logging with request IDs
threading through is fine" in the brief calls for, and it's immediately
usable by whatever already collects a container's logs (`docker logs`,
CloudWatch, etc.) without adding an external logging service as a new
dependency for a take-home prototype.

Request-scoped state (the request ID) is carried via `contextvars` rather
than threaded through every function's parameters -- that would mean
`get_customer_profile`, `mcp_client.call_tool`, `_execute_tool`, and every
other layer would need a `request_id` argument purely to pass it further
down. A context variable is the standard way to carry "ambient" per-request
context through an async call stack without polluting every signature.
"""

import contextvars
import json
import logging
import sys
from typing import Any

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

_LOGGER_NAME = "acme"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "event": record.getMessage(),
            "request_id": _request_id_var.get(),
        }
        extra_fields = getattr(record, "fields", None)
        if extra_fields:
            payload.update(extra_fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Call once at process startup. Routes all `logging` calls through the
    JSON formatter to stdout, so `docker logs acme_app` shows structured,
    greppable JSON lines instead of free-text log messages.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # uvicorn's own access logger is left alone -- it already logs each
    # request line; our middleware (main.py) adds the structured
    # request_start/request_end/request_error events with the request_id,
    # latency, and tool-call linkage that plain access logs don't carry.


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> str | None:
    return _request_id_var.get()


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Log one structured event with arbitrary key-value fields, tagged
    with the current request's id automatically (via the context var, so
    callers never need to pass it in themselves).
    """
    logging.getLogger(_LOGGER_NAME).log(level, event, extra={"fields": fields})
