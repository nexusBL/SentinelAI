from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class SentinelLogFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        del datefmt
        return datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record)
        message = record.getMessage()
        context = self._extract_context(record)
        if context:
            return (
                f"{timestamp} | {record.levelname:<8} | {record.name} | "
                f"{message} | {json.dumps(context, sort_keys=True, default=str)}"
            )
        return f"{timestamp} | {record.levelname:<8} | {record.name} | {message}"

    def _extract_context(self, record: logging.LogRecord) -> dict[str, Any]:
        ignored = {
            "args",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "taskName",
            "thread",
            "threadName",
        }
        return {
            key: value
            for key, value in record.__dict__.items()
            if key not in ignored and not key.startswith("_")
        }


class SentinelLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        merged_extra = dict(self.extra)
        merged_extra.update(kwargs.get("extra", {}))
        kwargs["extra"] = merged_extra
        return msg, kwargs


def configure_logging(level: int = logging.INFO) -> None:
    logger = logging.getLogger("sentinelai")
    if logger.handlers:
        logger.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(SentinelLogFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def get_logger(
    name: str,
    *,
    phase: str | None = None,
    run_id: str | None = None,
    graph_node: str | None = None,
) -> SentinelLoggerAdapter:
    configure_logging()
    logger = logging.getLogger(f"sentinelai.{name}")
    context = {
        "phase": phase,
        "run_id": run_id,
        "graph_node": graph_node,
    }
    return SentinelLoggerAdapter(
        logger,
        {key: value for key, value in context.items() if value is not None},
    )


def bind_logger(
    logger: SentinelLoggerAdapter,
    **context: Any,
) -> SentinelLoggerAdapter:
    merged_context = dict(logger.extra)
    merged_context.update({key: value for key, value in context.items() if value is not None})
    return SentinelLoggerAdapter(logger.logger, merged_context)


def log_event(
    logger: SentinelLoggerAdapter,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    payload = {"event": event}
    payload.update({key: value for key, value in fields.items() if value is not None})
    logger.log(level, event, extra=payload)
