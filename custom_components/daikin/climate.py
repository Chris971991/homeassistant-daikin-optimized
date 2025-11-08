"""Support for the Daikin HVAC."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    ATTR_SWING_MODE,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_INSIDE_TEMPERATURE,
    ATTR_OUTSIDE_TEMPERATURE,
    ATTR_STATE_OFF,
    ATTR_STATE_ON,
    ATTR_TARGET_TEMPERATURE,
)
from .coordinator import DaikinConfigEntry, DaikinCoordinator
from .entity import DaikinEntity

_LOGGER = logging.getLogger(__name__)


HA_STATE_TO_DAIKIN = {
    HVACMode.FAN_ONLY: "fan",
    HVACMode.DRY: "dry",
    HVACMode.COOL: "cool",
    HVACMode.HEAT: "hot",
    HVACMode.HEAT_COOL: "auto",
    HVACMode.OFF: "off",
}

DAIKIN_TO_HA_STATE = {
    "fan": HVACMode.FAN_ONLY,
    "dry": HVACMode.DRY,
    "cool": HVACMode.COOL,
    "hot": HVACMode.HEAT,
    "auto": HVACMode.HEAT_COOL,
    "off": HVACMode.OFF,
}

HA_STATE_TO_CURRENT_HVAC = {
    HVACMode.COOL: HVACAction.COOLING,
    HVACMode.HEAT: HVACAction.HEATING,
    HVACMode.OFF: HVACAction.OFF,
}

HA_PRESET_TO_DAIKIN = {
    PRESET_AWAY: "on",
    PRESET_NONE: "off",
    PRESET_BOOST: "powerful",
    PRESET_ECO: "econo",
}

HA_ATTR_TO_DAIKIN = {
    ATTR_PRESET_MODE: "en_hol",
    ATTR_HVAC_MODE: "mode",
    ATTR_FAN_MODE: "f_rate",
    ATTR_SWING_MODE: "f_dir",
    ATTR_INSIDE_TEMPERATURE: "htemp",
    ATTR_OUTSIDE_TEMPERATURE: "otemp",
    ATTR_TARGET_TEMPERATURE: "stemp",
}

DAIKIN_ATTR_ADVANCED = "adv"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaikinConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Daikin climate based on config_entry."""
    daikin_api = entry.runtime_data
    async_add_entities([DaikinClimate(daikin_api)])


def format_target_temperature(target_temperature: float) -> str:
    """Format target temperature to be sent to the Daikin unit, rounding to nearest half degree."""
    return str(round(float(target_temperature) * 2, 0) / 2).rstrip("0").rstrip(".")


class DaikinClimate(DaikinEntity, ClimateEntity):
    """Representation of a Daikin HVAC."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = list(HA_STATE_TO_DAIKIN)
    _attr_target_temperature_step = 1
    _attr_fan_modes: list[str]
    _attr_swing_modes: list[str]

    def __init__(self, coordinator: DaikinCoordinator) -> None:
        """Initialize the climate device."""
        super().__init__(coordinator)
        self._attr_fan_modes = self.device.fan_rate
        self._attr_swing_modes = self.device.swing_modes
        self._list: dict[str, list[Any]] = {
            ATTR_HVAC_MODE: self._attr_hvac_modes,
            ATTR_FAN_MODE: self._attr_fan_modes,
            ATTR_SWING_MODE: self._attr_swing_modes,
        }

        # Optimistic state for instant UI updates (devices are slow to respond)
        self._optimistic_target_temp = None
        self._optimistic_hvac_mode = None
        self._optimistic_fan_mode = None
        self._optimistic_swing_mode = None

        self._attr_supported_features = (
            ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TARGET_TEMPERATURE
        )

        if self.device.support_away_mode or self.device.support_advanced_modes:
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE

        if self.device.support_fan_rate:
            self._attr_supported_features |= ClimateEntityFeature.FAN_MODE

        if self.device.support_swing_mode:
            self._attr_supported_features |= ClimateEntityFeature.SWING_MODE

    async def _set(self, settings: dict[str, Any]) -> None:
        """Set device settings using API."""
        values: dict[str, Any] = {}

        for attr in (ATTR_TEMPERATURE, ATTR_FAN_MODE, ATTR_SWING_MODE, ATTR_HVAC_MODE):
            if (value := settings.get(attr)) is None:
                continue

            if (daikin_attr := HA_ATTR_TO_DAIKIN.get(attr)) is not None:
                if attr == ATTR_HVAC_MODE:
                    values[daikin_attr] = HA_STATE_TO_DAIKIN[value]
                elif value in self._list[attr]:
                    values[daikin_attr] = value.lower()
                else:
                    _LOGGER.error("Invalid value %s for %s", attr, value)

            # temperature
            elif attr == ATTR_TEMPERATURE:
                try:
                    values[HA_ATTR_TO_DAIKIN[ATTR_TARGET_TEMPERATURE]] = (
                        format_target_temperature(value)
                    )
                except ValueError:
                    _LOGGER.error("Invalid temperature %s", value)

        if values:
            # Store optimistic values for instant UI feedback
            if ATTR_TEMPERATURE in settings:
                self._optimistic_target_temp = settings[ATTR_TEMPERATURE]
            if ATTR_HVAC_MODE in settings:
                self._optimistic_hvac_mode = settings[ATTR_HVAC_MODE]
            if ATTR_FAN_MODE in settings:
                self._optimistic_fan_mode = settings[ATTR_FAN_MODE]
            if ATTR_SWING_MODE in settings:
                self._optimistic_swing_mode = settings[ATTR_SWING_MODE]

            # Trigger immediate UI update
            self.async_write_ha_state()

            try:
                await self.device.set(values)

                # Immediately request a refresh to get the latest state
                # This reduces perceived lag from 60s → ~1-2s
                await self.coordinator.async_request_refresh()
            except Exception as e:
                # Check if this is a network timeout or cancellation
                error_msg = str(e)
                if "timeout" in error_msg.lower() or "cancel" in error_msg.lower():
                    _LOGGER.warning("Network timeout communicating with device: %s", error_msg)
                else:
                    _LOGGER.error("Error setting device values: %s", e, exc_info=True)

                # Clear optimistic state on failure
                self._optimistic_target_temp = None
                self._optimistic_hvac_mode = None
                self._optimistic_fan_mode = None
                self._optimistic_swing_mode = None
                self.async_write_ha_state()
                raise

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self.device.mac

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self.device.inside_temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        # Return optimistic value if set, otherwise actual device value
        if self._optimistic_target_temp is not None:
            return self._optimistic_target_temp
        return self.device.target_temperature

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        await self._set(kwargs)

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current state."""
        ret = HA_STATE_TO_CURRENT_HVAC.get(self.hvac_mode)
        if (
            ret in (HVACAction.COOLING, HVACAction.HEATING)
            and self.device.support_compressor_frequency
            and self.device.compressor_frequency == 0
        ):
            return HVACAction.IDLE
        return ret

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation ie. heat, cool, idle."""
        # Return optimistic value if set, otherwise actual device value
        if self._optimistic_hvac_mode is not None:
            return self._optimistic_hvac_mode
        daikin_mode = self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_HVAC_MODE])[1]
        return DAIKIN_TO_HA_STATE.get(daikin_mode, HVACMode.HEAT_COOL)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        await self._set({ATTR_HVAC_MODE: hvac_mode})

    @property
    def fan_mode(self) -> str:
        """Return the fan setting."""
        # Return optimistic value if set, otherwise actual device value
        if self._optimistic_fan_mode is not None:
            return self._optimistic_fan_mode
        return self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_FAN_MODE])[1].title()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""
        await self._set({ATTR_FAN_MODE: fan_mode})

    @property
    def swing_mode(self) -> str:
        """Return the fan setting."""
        # Return optimistic value if set, otherwise actual device value
        if self._optimistic_swing_mode is not None:
            return self._optimistic_swing_mode
        return self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_SWING_MODE])[1].title()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target temperature."""
        await self._set({ATTR_SWING_MODE: swing_mode})

    @property
    def preset_mode(self) -> str:
        """Return the preset_mode."""
        if (
            self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_PRESET_MODE])[1]
            == HA_PRESET_TO_DAIKIN[PRESET_AWAY]
        ):
            return PRESET_AWAY
        if (
            HA_PRESET_TO_DAIKIN[PRESET_BOOST]
            in self.device.represent(DAIKIN_ATTR_ADVANCED)[1]
        ):
            return PRESET_BOOST
        if (
            HA_PRESET_TO_DAIKIN[PRESET_ECO]
            in self.device.represent(DAIKIN_ATTR_ADVANCED)[1]
        ):
            return PRESET_ECO
        return PRESET_NONE

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode."""
        if preset_mode == PRESET_AWAY:
            await self.device.set_holiday(ATTR_STATE_ON)
        elif preset_mode == PRESET_BOOST:
            await self.device.set_advanced_mode(
                HA_PRESET_TO_DAIKIN[PRESET_BOOST], ATTR_STATE_ON
            )
        elif preset_mode == PRESET_ECO:
            await self.device.set_advanced_mode(
                HA_PRESET_TO_DAIKIN[PRESET_ECO], ATTR_STATE_ON
            )
        elif self.preset_mode == PRESET_AWAY:
            await self.device.set_holiday(ATTR_STATE_OFF)
        elif self.preset_mode == PRESET_BOOST:
            await self.device.set_advanced_mode(
                HA_PRESET_TO_DAIKIN[PRESET_BOOST], ATTR_STATE_OFF
            )
        elif self.preset_mode == PRESET_ECO:
            await self.device.set_advanced_mode(
                HA_PRESET_TO_DAIKIN[PRESET_ECO], ATTR_STATE_OFF
            )

        # Immediately request a refresh to get the latest state
        await self.coordinator.async_request_refresh()
    @property
    def preset_modes(self) -> list[str]:
        """List of available preset modes."""
        ret = [PRESET_NONE]
        if self.device.support_away_mode:
            ret.append(PRESET_AWAY)
        if self.device.support_advanced_modes:
            ret += [PRESET_ECO, PRESET_BOOST]
        return ret

    async def async_turn_on(self) -> None:
        """Turn device on."""
        await self.device.set({})

    async def async_turn_off(self) -> None:
        """Turn device off."""
        await self.device.set(
            {HA_ATTR_TO_DAIKIN[ATTR_HVAC_MODE]: HA_STATE_TO_DAIKIN[HVACMode.OFF]}
        )

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Only clear optimistic state if device confirms the change
        # This prevents flickering when the device hasn't processed the command yet

        if self._optimistic_target_temp is not None:
            if abs(self.device.target_temperature - self._optimistic_target_temp) < 0.1:
                self._optimistic_target_temp = None

        if self._optimistic_hvac_mode is not None:
            device_mode = DAIKIN_TO_HA_STATE.get(
                self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_HVAC_MODE])[1]
            )
            if device_mode == self._optimistic_hvac_mode:
                self._optimistic_hvac_mode = None

        if self._optimistic_fan_mode is not None:
            device_fan = self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_FAN_MODE])[1].title()
            if device_fan == self._optimistic_fan_mode:
                self._optimistic_fan_mode = None

        if self._optimistic_swing_mode is not None:
            device_swing = self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_SWING_MODE])[1].title()
            if device_swing == self._optimistic_swing_mode:
                self._optimistic_swing_mode = None

        super()._handle_coordinator_update()
