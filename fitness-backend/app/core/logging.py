"""Structured logging setup (Phase 7)."""

from __future__ import annotations

import logging
import sys
from typing import Any, cast

import structlog
from structlog.typing import FilteringBoundLogger

_CONFIGURED = False


def reset_logging_configuration_for_tests() -> None:
    """Reset global logging configuration (tests only)."""
    global _CONFIGURED
    _CONFIGURED = False


def configure_logging(*, debug: bool) -> None:
    """Configure structlog for JSON logs on stdout (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=shared_processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    """Return a structlog logger, optionally with a ``logger`` name bound."""
    logger = cast(FilteringBoundLogger, structlog.get_logger())
    if name is not None:
        return logger.bind(logger=name)
    return logger


def bind_request_context(**kwargs: Any) -> None:
    """Bind keys into the structlog contextvars (e.g. ``request_id``, ``user_id``)."""
    structlog.contextvars.bind_contextvars(**kwargs)


def reset_request_context() -> None:
    """Clear request-scoped context (call at end of request)."""
    structlog.contextvars.clear_contextvars()
