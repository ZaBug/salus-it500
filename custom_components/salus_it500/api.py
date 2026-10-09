"""Async client for the Salus iT500 cloud API (the Arrayent backend of the mobile app).

No Home Assistant imports: the session is injected, so the module is testable on
its own. Protocol reference: RichyA/pyit500 (MIT).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_HOST = "https://sal-emea-p01-api.arrayent.com"
LOGIN_URL = f"{API_HOST}/acc/applications/SalusService/sessions"
ZAMAPI_URL = f"{API_HOST}/zdk/services/zamapi"

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
RETRY_DELAYS = (1, 3)

# requestFault error codes seen on the live API.
ERROR_INVALID_TOKEN = 106
ERROR_DEVICE_NOT_FOUND = 109
AUTH_ERROR_CODES = {ERROR_INVALID_TOKEN}


class SalusError(Exception):
    """Base error."""


class SalusAuthError(SalusError):
    """Credentials rejected."""


class SalusConnectionError(SalusError):
    """Network problem or server error after retries."""


class SalusApiError(SalusError):
    """The API answered with an error code."""

    def __init__(self, code: int | None, message: str) -> None:
        super().__init__(f"{message} (code {code})")
        self.code = code


@dataclass(frozen=True, slots=True)
class Attribute:
    """One device attribute as reported by the cloud."""

    value: str
    updated_ms: int  # epoch milliseconds of the last device report, 0 if never


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Device from the account's device list."""

    device_id: str
    name: str
    type_id: str


def hash_password(password: str) -> str:
    """The API expects the MD5 hex digest of the password."""
    return hashlib.md5(password.encode()).hexdigest()  # noqa: S324 - protocol requirement


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, name: str) -> str:
    for child in element:
        if _local(child.tag) == name:
            return (child.text or "").strip()
    return ""


def parse_fault(text: str) -> SalusApiError | None:
    """Return the error carried by a requestFault document, if any."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    if _local(root.tag) != "requestFault":
        return None
    code = _child_text(root, "errorCode")
    return SalusApiError(int(code) if code.isdigit() else None, _child_text(root, "errorMsg"))


def parse_attributes(text: str) -> dict[str, Attribute]:
    """Parse a getDeviceAttributesWithValues response."""
    root = ET.fromstring(text)
    attributes: dict[str, Attribute] = {}
    for element in root:
        if _local(element.tag) != "attrList":
            continue
        name = _child_text(element, "name")
        if not name:
            continue
        updated = _child_text(element, "updTime")
        attributes[name] = Attribute(
            value=_child_text(element, "value"),
            updated_ms=int(updated) if updated.isdigit() else 0,
        )
    return attributes


def parse_device_list(text: str) -> list[DeviceInfo]:
    """Parse a getDeviceList response."""
    root = ET.fromstring(text)
    return [
        DeviceInfo(
            device_id=_child_text(element, "devId"),
            name=_child_text(element, "devName"),
            type_id=_child_text(element, "typeId"),
        )
        for element in root
        if _local(element.tag) == "devList"
    ]


def parse_ret_code(text: str) -> int:
    """Return retCode of a setMultiDeviceAttributes2 response."""
    root = ET.fromstring(text)
    code = _child_text(root, "retCode")
    if not code.lstrip("-").isdigit():
        raise SalusApiError(None, f"Unexpected set response: {text[:200]}")
    return int(code)


class SalusClient:
    """Session against the Salus cloud. One instance per account."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password_hash = hash_password(password)
        self._user_id: str | None = None
        self._token: str | None = None
        self._lock = asyncio.Lock()

    @property
    def user_id(self) -> str | None:
        """User id of the logged-in account."""
        return self._user_id

    def reset_session(self) -> None:
        """Drop the token; the next call logs in again."""
        self._token = None

    async def login(self) -> None:
        """Get a new security token."""
        try:
            async with self._session.post(
                LOGIN_URL,
                json={"username": self._username, "password": self._password_hash},
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                text = await resp.text()
                status = resp.status
        except (aiohttp.ClientError, TimeoutError) as err:
            raise SalusConnectionError(f"Login request failed: {err}") from err
        try:
            data: dict[str, Any] = json.loads(text)
        except ValueError:
            data = {}
        if status in (401, 403) or "errorCode" in data:
            raise SalusAuthError(data.get("errorMessage") or f"Login rejected (HTTP {status})")
        if status != 200 or "securityToken" not in data:
            raise SalusConnectionError(f"Unexpected login response (HTTP {status})")
        self._user_id = str(data["userId"])
        self._token = str(data["securityToken"])

    async def _call(self, method: str, path: str, params: dict[str, str]) -> str:
        """One zamapi call with token refresh and retries on transient errors."""
        last_error: SalusError | None = None
        relogged = False
        for delay in (0, *RETRY_DELAYS):
            if delay:
                await asyncio.sleep(delay)
            if self._token is None:
                await self.login()
            query = {**params, "secToken": self._token or "", "userId": self._user_id or ""}
            try:
                if method == "get":
                    request = self._session.get(f"{ZAMAPI_URL}/{path}", params=query, timeout=REQUEST_TIMEOUT)
                else:
                    request = self._session.post(f"{ZAMAPI_URL}/{path}", data=query, timeout=REQUEST_TIMEOUT)
                async with request as resp:
                    text = await resp.text()
                    status = resp.status
            except (aiohttp.ClientError, TimeoutError) as err:
                last_error = SalusConnectionError(f"{path} failed: {err}")
                continue
            if status == 200:
                return text
            fault = parse_fault(text)
            if (fault and fault.code in AUTH_ERROR_CODES) or status in (401, 403):
                if relogged:
                    raise SalusAuthError("Security token rejected after a fresh login")
                _LOGGER.debug("Security token rejected, logging in again")
                self._token = None
                relogged = True
                continue
            if fault and fault.code is not None:
                raise fault
            last_error = SalusConnectionError(f"{path} returned HTTP {status}")
        raise last_error or SalusConnectionError(f"{path} failed")

    async def async_get_devices(self) -> list[DeviceInfo]:
        """Devices registered on the account."""
        async with self._lock:
            return parse_device_list(await self._call("post", "getDeviceList", {}))

    async def async_get_attributes(self, device_id: str) -> dict[str, Attribute]:
        """All attributes of a device, as last reported to the cloud."""
        async with self._lock:
            text = await self._call("post", "getDeviceAttributesWithValues", {"devId": device_id})
        return parse_attributes(text)

    async def async_set_attribute(self, device_id: str, name: str, value: str | int) -> None:
        """Set one attribute. The iT500 reports multiAttributeCapable=false, so one per call."""
        async with self._lock:
            text = await self._call(
                "get",
                "setMultiDeviceAttributes2",
                {"devId": device_id, "name1": name, "value1": str(value)},
            )
        code = parse_ret_code(text)
        if code != 0:
            raise SalusApiError(code, f"Setting {name}={value} was refused")
