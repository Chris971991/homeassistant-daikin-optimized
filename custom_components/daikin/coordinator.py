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

from .const import (
    COORDINATOR_UPDATE_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    FAILED_POLLS_TOLERATED,
)

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
        # v2.42.0: count of consecutive failed polls. pydaikin applies every
        # resource that DID succeed before raising, so the device values are
        # as fresh as the network allowed even on a failed poll.
        self._consecutive_failures = 0

    def _tolerate_or_raise(self, message: str, err: BaseException) -> None:
        """Swallow the first FAILED_POLLS_TOLERATED consecutive failures.

        The entity keeps its last state and stays available; the next
        failure in a row raises UpdateFailed exactly as before, so a real
        outage still marks the entity unavailable and still arms the
        climate entity's coordinator-recovery reconnect grace.
        """
        self._consecutive_failures += 1
        if self._consecutive_failures <= FAILED_POLLS_TOLERATED:
            _LOGGER.info(
                "%s (failed poll %d of %d tolerated; keeping last state)",
                message,
                self._consecutive_failures,
                FAILED_POLLS_TOLERATED,
            )
            return
        raise UpdateFailed(message) from err

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
            self._tolerate_or_raise(f"Timeout communicating with {name}", err)
        except DaikinException as err:
            self._tolerate_or_raise(f"Error communicating with {name}: {err}", err)
        except (ClientError, ValueError) as err:
            self._tolerate_or_raise(f"Error communicating with {name}: {err!r}", err)
        else:
            self._consecutive_failures = 0
