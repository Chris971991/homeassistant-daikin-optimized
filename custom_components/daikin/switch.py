"""Support for Daikin AirBase zones."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import DaikinConfigEntry, DaikinCoordinator
from .entity import DaikinEntity

_LOGGER = logging.getLogger(__name__)

DAIKIN_ATTR_ADVANCED = "adv"
DAIKIN_ATTR_STREAMER = "streamer"
DAIKIN_ATTR_MODE = "mode"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaikinConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Daikin climate based on config_entry."""
    daikin_api = entry.runtime_data
    switches: list[SwitchEntity] = []
    if zones := daikin_api.device.zones:
        switches.extend(
            DaikinZoneSwitch(daikin_api, zone_id)
            for zone_id, zone in enumerate(zones)
            if zone[0] != "-"
        )
    if daikin_api.device.support_advanced_modes:
        # It isn't possible to find out from the API responses if a specific
        # device supports the streamer, so assume so if it does support
        # advanced modes.
        switches.append(DaikinStreamerSwitch(daikin_api))
    switches.append(DaikinToggleSwitch(daikin_api))
    async_add_entities(switches)


class DaikinZoneSwitch(DaikinEntity, SwitchEntity):
    """Representation of a zone."""

    _attr_translation_key = "zone"

    def __init__(self, coordinator: DaikinCoordinator, zone_id: int) -> None:
        """Initialize the zone."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._attr_unique_id = f"{self.device.mac}-zone{zone_id}"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self.device.zones[self._zone_id][0]

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor."""
        return self.device.zones[self._zone_id][1] == "1"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the zone on."""
        await self.device.set_zone(self._zone_id, "zone_onoff", "1")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the zone off."""
        await self.device.set_zone(self._zone_id, "zone_onoff", "0")


class DaikinStreamerSwitch(DaikinEntity, SwitchEntity):
    """Streamer state."""

    _attr_name = "Streamer"
    _attr_translation_key = "streamer"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.device.mac}-streamer"

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor."""
        return DAIKIN_ATTR_STREAMER in self.device.represent(DAIKIN_ATTR_ADVANCED)[1]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the zone on."""
        await self.device.set_streamer("on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the zone off."""
        await self.device.set_streamer("off")


class DaikinToggleSwitch(DaikinEntity, SwitchEntity):
    """Switch state."""

    _attr_translation_key = "toggle"

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.device.mac}-toggle"

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor."""
        return "off" not in self.device.represent(DAIKIN_ATTR_MODE)

    def _climate_entity_id(self) -> str | None:
        """Return the climate entity for this device (unique_id IS device.mac)."""
        return er.async_get(self.hass).async_get_entity_id(
            "climate", DOMAIN, self.device.mac
        )

    def _usable_climate_entity_id(self) -> str | None:
        """Return the climate entity_id only if it is actually loaded.

        A disabled/unloaded climate entity still resolves in the registry, but
        a blocking service call against it silently no-ops — so also require a
        live state object before routing through the climate services.
        """
        entity_id = self._climate_entity_id()
        if entity_id is not None and self.hass.states.get(entity_id) is not None:
            return entity_id
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on.

        Route through the climate entity's turn_on service so all override
        bookkeeping (_last_any_command_time, expected state, optimistic UI,
        last-active-mode restore) applies in one place — calling device.set()
        directly here fired false physical-remote overrides.
        """
        if (entity_id := self._usable_climate_entity_id()) is not None:
            await self.hass.services.async_call(
                "climate",
                SERVICE_TURN_ON,
                {ATTR_ENTITY_ID: entity_id},
                blocking=True,
            )
            return
        _LOGGER.warning(
            "Climate entity not found or not loaded for %s, sending raw command",
            self.device.mac,
        )
        await self.device.set({DAIKIN_ATTR_MODE: "auto"})

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off.

        Routed through climate.turn_off for the same bookkeeping reasons as
        async_turn_on.
        """
        if (entity_id := self._usable_climate_entity_id()) is not None:
            await self.hass.services.async_call(
                "climate",
                SERVICE_TURN_OFF,
                {ATTR_ENTITY_ID: entity_id},
                blocking=True,
            )
            return
        _LOGGER.warning(
            "Climate entity not found or not loaded for %s, sending raw command",
            self.device.mac,
        )
        await self.device.set({DAIKIN_ATTR_MODE: "off"})
