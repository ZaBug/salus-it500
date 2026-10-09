"""Minimal stand-in for aiohttp.ClientSession driven by a queue of responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeResponse:
    status: int
    body: str

    async def text(self) -> str:
        return self.body

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


@dataclass
class FakeSession:
    """Answers each request with the next queued item (FakeResponse or exception)."""

    queue: list[Any] = field(default_factory=list)
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def _next(self, method: str, url: str, kwargs: dict[str, Any]) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        item = self.queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._next("post", url, kwargs)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._next("get", url, kwargs)
