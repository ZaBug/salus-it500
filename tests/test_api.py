"""SalusClient against a scripted fake session."""

from __future__ import annotations

import aiohttp
import pytest

from conftest import api, fixture_text
from fakes import FakeResponse, FakeSession

LOGIN_OK = FakeResponse(200, '{"userId":987654,"securityToken":"tok1"}')
LOGIN_OK2 = FakeResponse(200, '{"userId":987654,"securityToken":"tok2"}')
BAD_TOKEN = FakeResponse(
    500,
    '<ns1:requestFault xmlns:ns1="http://arrayent.com/zamapi/"><errorCode>106</errorCode>'
    "<errorMsg>Invalid security token.</errorMsg></ns1:requestFault>",
)
NO_DEVICE = FakeResponse(
    500,
    '<ns1:requestFault xmlns:ns1="http://arrayent.com/zamapi/"><errorCode>109</errorCode>'
    "<errorMsg>Device does not exist.</errorMsg></ns1:requestFault>",
)
SET_OK = FakeResponse(
    200,
    '<ns1:setMultiDeviceAttributes2Response xmlns:ns1="http://arrayent.com/zamapi/">'
    "<retCode>0</retCode></ns1:setMultiDeviceAttributes2Response>",
)


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(api, "RETRY_DELAYS", (0, 0))


def attributes_ok() -> FakeResponse:
    return FakeResponse(200, fixture_text("attributes.xml"))


def test_password_is_md5():
    assert api.hash_password("secret") == "5ebe2294ecd0e0f08eab7690d2a6ee69"


async def test_login_sends_hash_and_stores_token():
    session = FakeSession([LOGIN_OK])
    client = api.SalusClient(session, "user@example.com", "secret")
    await client.login()
    assert client.user_id == "987654"
    _, _, kwargs = session.calls[0]
    assert kwargs["json"] == {
        "username": "user@example.com",
        "password": api.hash_password("secret"),
    }


async def test_login_rejected():
    session = FakeSession(
        [FakeResponse(403, '{"errorCode":101,"errorMessage":"Invalid login name or password."}')]
    )
    with pytest.raises(api.SalusAuthError, match="Invalid login"):
        await api.SalusClient(session, "u", "p").login()


async def test_device_list():
    session = FakeSession([LOGIN_OK, FakeResponse(200, fixture_text("device_list.xml"))])
    devices = await api.SalusClient(session, "u", "p").async_get_devices()
    assert devices == [api.DeviceInfo(device_id="123456789", name="STA00000000", type_id="1")]
    assert session.calls[1][2]["data"]["secToken"] == "tok1"


async def test_expired_token_logs_in_again():
    session = FakeSession([LOGIN_OK, BAD_TOKEN, LOGIN_OK2, attributes_ok()])
    attrs = await api.SalusClient(session, "u", "p").async_get_attributes("123456789")
    assert attrs["A84"].value == "1750"
    assert session.calls[3][2]["data"]["secToken"] == "tok2"


async def test_token_rejected_twice_is_auth_error():
    session = FakeSession([LOGIN_OK, BAD_TOKEN, LOGIN_OK2, BAD_TOKEN])
    with pytest.raises(api.SalusAuthError):
        await api.SalusClient(session, "u", "p").async_get_attributes("1")


async def test_reset_session_forces_login():
    session = FakeSession([LOGIN_OK, attributes_ok(), LOGIN_OK2, attributes_ok()])
    client = api.SalusClient(session, "u", "p")
    await client.async_get_attributes("1")
    client.reset_session()
    await client.async_get_attributes("1")
    assert [call[1].rsplit("/", 1)[-1] for call in session.calls].count("sessions") == 2


async def test_api_fault_is_raised_without_retry():
    session = FakeSession([LOGIN_OK, NO_DEVICE])
    with pytest.raises(api.SalusApiError) as err:
        await api.SalusClient(session, "u", "p").async_get_attributes("1")
    assert err.value.code == api.ERROR_DEVICE_NOT_FOUND


async def test_transient_errors_are_retried():
    session = FakeSession(
        [
            LOGIN_OK,
            aiohttp.ClientConnectionError("boom"),
            FakeResponse(503, "busy"),
            attributes_ok(),
        ]
    )
    attrs = await api.SalusClient(session, "u", "p").async_get_attributes("1")
    assert "A85" in attrs


async def test_transient_errors_give_up():
    session = FakeSession([LOGIN_OK, TimeoutError(), TimeoutError(), TimeoutError()])
    with pytest.raises(api.SalusConnectionError):
        await api.SalusClient(session, "u", "p").async_get_attributes("1")


async def test_set_attribute_uses_get_and_checks_ret_code():
    session = FakeSession([LOGIN_OK, SET_OK])
    await api.SalusClient(session, "u", "p").async_set_attribute("1", "A85", 2100)
    method, url, kwargs = session.calls[1]
    assert method == "get"
    assert url.endswith("/setMultiDeviceAttributes2")
    assert kwargs["params"]["name1"] == "A85"
    assert kwargs["params"]["value1"] == "2100"


async def test_set_attribute_refused():
    refused = FakeResponse(200, SET_OK.body.replace("<retCode>0<", "<retCode>3<"))
    session = FakeSession([LOGIN_OK, refused])
    with pytest.raises(api.SalusApiError):
        await api.SalusClient(session, "u", "p").async_set_attribute("1", "A85", 2100)


def test_parse_attributes_reads_timestamps():
    attrs = api.parse_attributes(fixture_text("attributes.xml"))
    assert attrs["A84"].updated_ms > 0
    assert attrs["A94"] == api.Attribute("", 0)
