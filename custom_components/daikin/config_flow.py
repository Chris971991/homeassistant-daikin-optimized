"""Config flow for the Daikin platform."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from aiohttp import ClientError, web_exceptions
from pydaikin.daikin_base import Appliance
from pydaikin.discovery import Discovery
from pydaikin.exceptions import DaikinException
from pydaikin.factory import DaikinFactory
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PASSWORD, CONF_UUID
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.util.ssl import client_context_no_verify

from .const import DOMAIN, KEY_MAC, TIMEOUT

_LOGGER = logging.getLogger(__name__)


class FlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the Daikin config flow."""
        self.host: str | None = None

    @property
    def schema(self) -> vol.Schema:
        """Return current schema."""
        return vol.Schema(
            {
                vol.Required(CONF_HOST, default=self.host): str,
                vol.Optional(CONF_API_KEY): str,
                vol.Optional(CONF_PASSWORD): str,
            }
        )

    async def _create_entry(
        self,
        host: str,
        mac: str,
        key: str | None = None,
        uuid: str | None = None,
        password: str | None = None,
    ) -> ConfigFlowResult:
        """Register new entry."""
        if not self.unique_id:
            await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=host,
            data={
                CONF_HOST: host,
                KEY_MAC: mac,
                CONF_API_KEY: key,
                CONF_UUID: uuid,
                CONF_PASSWORD: password,
            },
        )

    async def _create_device(
        self, host: str, key: str | None = None, password: str | None = None
    ) -> ConfigFlowResult:
        """Create device."""
        # BRP07Cxx devices needs uuid together with key
        if key:
            uuid = str(uuid4())
        else:
            uuid = None
            key = None

        if not password:
            password = None

        try:
            async with asyncio.timeout(TIMEOUT):
                device: Appliance = await DaikinFactory(
                    host,
                    async_get_clientsession(self.hass),
                    key=key,
                    uuid=uuid,
                    password=password,
                    ssl_context=client_context_no_verify(),
                )
        except (TimeoutError, ClientError):
            self.host = None
            return self.async_show_form(
                step_id="user",
                data_schema=self.schema,
                errors={"base": "cannot_connect"},
            )
        except web_exceptions.HTTPForbidden:
            return self.async_show_form(
                step_id="user",
                data_schema=self.schema,
                errors={"base": "invalid_auth"},
            )
        except DaikinException as daikin_exp:
            _LOGGER.error(daikin_exp)
            return self.async_show_form(
                step_id="user",
                data_schema=self.schema,
                errors={"base": "unknown"},
            )
        except Exception:
            _LOGGER.exception("Unexpected error creating device")
            return self.async_show_form(
                step_id="user",
                data_schema=self.schema,
                errors={"base": "unknown"},
            )

        mac = device.mac
        return await self._create_entry(host, mac, key, uuid, password)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """User initiated config flow."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=self.schema)
        if user_input.get(CONF_API_KEY) and user_input.get(CONF_PASSWORD):
            self.host = user_input[CONF_HOST]
            return self.async_show_form(
                step_id="user",
                data_schema=self.schema,
                errors={"base": "api_password"},
            )
        return await self._create_device(
            user_input[CONF_HOST],
            user_input.get(CONF_API_KEY),
            user_input.get(CONF_PASSWORD),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is None:
            # Show form with current values
            self.host = entry.data.get(CONF_HOST)
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST)): str,
                        vol.Optional(CONF_API_KEY, default=entry.data.get(CONF_API_KEY, "")): str,
                        vol.Optional(CONF_PASSWORD, default=entry.data.get(CONF_PASSWORD, "")): str,
                    }
                ),
            )

        # Validate the new configuration
        if user_input.get(CONF_API_KEY) and user_input.get(CONF_PASSWORD):
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self.schema,
                errors={"base": "api_password"},
            )

        # Test connection with new credentials
        key = user_input.get(CONF_API_KEY) or None
        password = user_input.get(CONF_PASSWORD) or None
        uuid = str(uuid4()) if key else None

        try:
            async with asyncio.timeout(TIMEOUT):
                device: Appliance = await DaikinFactory(
                    user_input[CONF_HOST],
                    async_get_clientsession(self.hass),
                    key=key,
                    uuid=uuid,
                    password=password,
                    ssl_context=client_context_no_verify(),
                )
        except (TimeoutError, ClientError):
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self.schema,
                errors={"base": "cannot_connect"},
            )
        except Exception as err:
            _LOGGER.exception("Unexpected error during reconfigure: %s", err)
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self.schema,
                errors={"base": "unknown"},
            )

        # Update the config entry
        return self.async_update_reload_and_abort(
            entry,
            data={
                CONF_HOST: user_input[CONF_HOST],
                KEY_MAC: device.mac,
                CONF_API_KEY: key,
                CONF_UUID: uuid,
                CONF_PASSWORD: password,
            },
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Prepare configuration for a discovered Daikin device."""
        _LOGGER.debug("Zeroconf user_input: %s", discovery_info)
        devices = Discovery().poll(ip=discovery_info.host)
        if not devices:
            _LOGGER.debug(
                (
                    "Could not find MAC-address for %s, make sure the required UDP"
                    " ports are open (see integration documentation)"
                ),
                discovery_info.host,
            )
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(next(iter(devices))[KEY_MAC])
        self._abort_if_unique_id_configured()
        self.host = discovery_info.host
        return await self.async_step_user()
