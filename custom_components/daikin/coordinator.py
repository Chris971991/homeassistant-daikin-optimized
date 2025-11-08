"""Coordinator for Daikin integration."""

import asyncio
from datetime import timedelta
import logging

from pydaikin.daikin_base import Appliance
from pydaikin.exceptions import DaikinException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN

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
        try:
            await self.device.update_status()
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout communicating with {self.device.values.get('name', 'device')}") from err
        except DaikinException as err:
            raise UpdateFailed(f"Error communicating with {self.device.values.get('name', 'device')}: {err}") from err
