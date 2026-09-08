import logging
import re
from contextvars import ContextVar, Token
from uuid import uuid4

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_MAX_REQUEST_ID_LENGTH = 64


def resolve_request_id(incoming_request_id: str | None) -> str:
    if (
        incoming_request_id
        and len(incoming_request_id) <= _MAX_REQUEST_ID_LENGTH
        and _REQUEST_ID_PATTERN.fullmatch(incoming_request_id)
    ):
        return incoming_request_id

    return str(uuid4())


def set_request_id(request_id: str) -> Token[str]:
    return _request_id.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    _request_id.reset(token)


def get_request_id() -> str:
    return _request_id.get()


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True