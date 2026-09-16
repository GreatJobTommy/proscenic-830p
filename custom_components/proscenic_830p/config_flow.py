"""Config flow: ProscenicHome login (local_key) or manual Tuya LAN fields."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .adapter import find_host_for_gw_id
from .const import CONF_LOCAL_KEY, DEFAULT_NAME, DOMAIN
from .constants import KNOWN_DEVICE_ID, TUYA_VERSION
from .oem_cloud import (
    InvalidAuthentication,
    PasswordLocked,
    ProscenicOemError,
    RateLimited,
    discover_830p,
    request_login_code,
)

CONF_DEVICE_ID = "device_id"
CONF_REGION = "region"
CONF_NAME = "name"
CONF_COUNTRY_CODE = "country_code"
_LOGGER = logging.getLogger(__name__)


async def _lan_host(hass: HomeAssistant, device_id: str) -> str:
    host = await hass.async_add_executor_job(find_host_for_gw_id, device_id)
    return host or ""


class Proscenic830PConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._login_input: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            if user_input["mode"] == "manual":
                return await self.async_step_manual()
            return await self.async_step_login()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("mode", default="login"): vol.In(
                        {
                            "login": "ProscenicHome email code",
                            "manual": "Manual local_key",
                        }
                    )
                }
            ),
        )

    async def async_step_login(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._login_input = dict(user_input)
            try:
                await self.hass.async_add_executor_job(
                    lambda: request_login_code(
                        user_input[CONF_USERNAME],
                        country_code=str(user_input.get(CONF_COUNTRY_CODE, "49")),
                        region=user_input.get(CONF_REGION, "eu"),
                    )
                )
            except InvalidAuthentication as err:
                _LOGGER.warning("ProscenicHome code send rejected: %s", err)
                errors["base"] = "invalid_auth"
            except RateLimited as err:
                _LOGGER.warning("ProscenicHome rate limited: %s", err)
                errors["base"] = "too_frequent"
            except PasswordLocked as err:
                _LOGGER.warning("ProscenicHome password locked: %s", err)
                errors["base"] = "password_locked"
            except ProscenicOemError as err:
                _LOGGER.warning("ProscenicHome code send failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_otp()
        return self.async_show_form(
            step_id="login",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Optional(CONF_COUNTRY_CODE, default="49"): str,
                    vol.Optional(CONF_REGION, default="eu"): vol.In(["eu", "us", "cn", "in"]),
                }
            ),
            errors=errors,
        )

    async def async_step_otp(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                discovered = await self.hass.async_add_executor_job(
                    lambda: discover_830p(
                        self._login_input[CONF_USERNAME],
                        "",
                        region=self._login_input.get(CONF_REGION, "eu"),
                        country_code=str(self._login_input.get(CONF_COUNTRY_CODE, "49")),
                        device_id=KNOWN_DEVICE_ID,
                        email_code=str(user_input.get("otp_code", "")).strip(),
                    )
                )
            except InvalidAuthentication as err:
                _LOGGER.warning("ProscenicHome code rejected: %s", err)
                errors["base"] = "invalid_auth"
            except RateLimited as err:
                _LOGGER.warning("ProscenicHome rate limited: %s", err)
                errors["base"] = "too_frequent"
            except ProscenicOemError as err:
                _LOGGER.warning("ProscenicHome discover failed: %s", err)
                if "no Proscenic 830P" in str(err):
                    errors["base"] = "no_device"
                else:
                    errors["base"] = "cannot_connect"
            else:
                host = discovered.get("host") or await _lan_host(
                    self.hass, discovered["device_id"]
                )
                if not host:
                    host = "192.168.178.63"
                return await self._create(discovered["name"], host, discovered)
        return self.async_show_form(
            step_id="otp",
            data_schema=vol.Schema({vol.Required("otp_code"): str}),
            errors=errors,
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            data = {
                "name": user_input.get(CONF_NAME, DEFAULT_NAME),
                "host": user_input[CONF_HOST],
                "device_id": user_input[CONF_DEVICE_ID],
                "local_key": user_input[CONF_LOCAL_KEY],
                "uuid": "",
            }
            return await self._create(data["name"], data["host"], data)
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default="192.168.178.63"): str,
                    vol.Required(CONF_DEVICE_ID, default=KNOWN_DEVICE_ID): str,
                    vol.Required(CONF_LOCAL_KEY): str,
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                }
            ),
        )

    async def _create(self, name: str, host: str, discovered: dict[str, str]):
        await self.async_set_unique_id(discovered["device_id"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=name or DEFAULT_NAME,
            data={
                CONF_HOST: host,
                CONF_DEVICE_ID: discovered["device_id"],
                CONF_LOCAL_KEY: discovered["local_key"],
                "uuid": discovered.get("uuid", ""),
                CONF_NAME: name or DEFAULT_NAME,
                "version": TUYA_VERSION,
            },
        )
