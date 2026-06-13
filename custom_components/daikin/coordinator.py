"""Coordinator for Daikin integration."""

import asyncio
from datetime import timedelta
import logging

from aiohttp import ClientError
from aiohttp.web_exceptions import HTTPForbidden
from pydaikin.daikin_base import Appliance
from pydaikin.exceptions import DaikinException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import COORDINATOR_UPDATE_TIMEOUT, DEFAULT_UPDATE_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type DaikinConfigEntry = ConfigEntry[DaikinCoordinator]


class DaikinCoordinator(DataUpdateCoordinator[None]):
    """Class to manage fetching Daikin data."""

    def __init__(
        self, hass: HomeAssistant, entry: DaikinConfigEntry, device: Appliance
    ) -> None:
        """Initialize global Daikin data updater."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=device.values.get("name", DOMAIN),
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )
        self.device = device

    async def _async_update_data(self) -> None:
        """Fetch data from Daikin device."""
        name = self.device.values.get("name", "device")
        try:
            async with asyncio.timeout(COORDINATOR_UPDATE_TIMEOUT):
                await self.device.update_status()
        except HTTPForbidden as err:
            # pydaikin raises HTTPForbidden on a genuine 403 — credentials are
            # wrong/expired, so suspend polling and start reauth.
            # Cross-cluster contract: for multi-resource base-class devices this
            # only fires once pydaikin's H3 fix lands (TaskGroup currently
            # swallows single-task failures); the mapping is correct to land now.
            raise ConfigEntryAuthFailed(f"Authentication failed for {name}") from err
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout communicating with {name}") from err
        except DaikinException as err:
            raise UpdateFailed(f"Error communicating with {name}: {err}") from err
        except (ClientError, ValueError) as err:
            raise UpdateFailed(f"Error communicating with {name}: {err!r}") from err
