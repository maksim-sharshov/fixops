import uuid
from contextvars import ContextVar

from fastapi import Request

request_id: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)


async def request_id_middleware(
    request: Request,
    call_next,
):

    request_id_value = str(uuid.uuid4())

    request_id.set(request_id_value)

    response = await call_next(request)

    response.headers[
        "X-Request-ID"
    ] = request_id_value

    return response
