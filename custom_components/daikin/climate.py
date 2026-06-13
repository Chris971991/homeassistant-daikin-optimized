"""Support for the Daikin HVAC."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

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
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pydaikin.exceptions import DaikinException

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
    _attr_target_temperature_step = 0.5
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
        self._optimistic_set_time = None  # Timestamp to detect stale optimistic values

        # Track last known power state for physical remote override detection
        # Initialize from device state to enable detection on first command after HA restart
        self._last_known_pow: str = self.device.values.get('pow', '1')
        # Debounce: prevent duplicate override events from race conditions
        self._last_override_event_time: float | None = None
        # Track entity initialization time for startup grace period (timezone-aware)
        self._entity_init_time: str = dt_util.now().isoformat()
        # v2.36.0: Float timestamp for efficient startup grace comparison in override detection
        self._entity_init_timestamp: float = time.time()
        # v2.36.0: Track coordinator state for reconnect-grace logic.
        # Init from current coordinator state (not hardcoded True) — first_refresh
        # has already completed at this point per HA setup ordering, so this reflects reality.
        self._last_coordinator_success: bool = self.coordinator.last_update_success
        self._last_coordinator_recovery_time: float | None = None
        # v2.37.0: Track ANY command sent (not just on/off) to suppress false override
        # during mode transitions where Daikin bounces pow 1→0→1 (e.g., cool→fan_only)
        self._last_any_command_time: float | None = None

        # v2.36.0: Persistent expected state for blueprint override detection.
        # Unlike optimistic state (clears after 30s), these persist for up to 1 hour
        # so the blueprint can detect manual overrides well after the last command.
        self._expected_hvac_mode: str | None = None
        self._expected_set_time: float | None = None
        # v2.40.0: Snapshot of expected state from before the in-flight command,
        # restored if that command fails (a failed command must not blind the
        # blueprint's expected-vs-actual safety net).
        self._expected_state_snapshot: tuple[str | None, float | None] | None = None
        # v2.40.0: Last coordinator-CONFIRMED active (non-off) HVAC mode.
        # Written only in _handle_coordinator_update, mirroring _last_known_pow.
        # Used by async_turn_on to restore the pre-off mode.
        self._last_active_hvac_mode: HVACMode | None = None

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

    def _record_expected_state(self, hvac_mode: HVACMode | str) -> None:
        """Record expected HVAC mode for the blueprint's safety-net detection.

        Snapshots the previous expected state first so a failed command can
        roll back to the last truthful value instead of wiping it.
        Called BEFORE _set() so the record survives mode:restart cancellation.
        """
        self._expected_state_snapshot = (
            self._expected_hvac_mode,
            self._expected_set_time,
        )
        self._expected_hvac_mode = (
            hvac_mode.value if isinstance(hvac_mode, HVACMode) else str(hvac_mode)
        )
        self._expected_set_time = time.time()

    async def _set(self, settings: dict[str, Any]) -> None:
        """Set device settings using API."""
        # NOTE: Removed Override mode blocking - it was blocking ALL commands including
        # user commands. The blueprint already handles Override mode by not sending
        # automation commands. User commands should ALWAYS go through.

        values: dict[str, Any] = {}

        for attr in (ATTR_TEMPERATURE, ATTR_FAN_MODE, ATTR_SWING_MODE, ATTR_HVAC_MODE):
            if (value := settings.get(attr)) is None:
                continue

            if (daikin_attr := HA_ATTR_TO_DAIKIN.get(attr)) is not None:
                if attr == ATTR_HVAC_MODE:
                    values[daikin_attr] = HA_STATE_TO_DAIKIN[value]
                elif value in self._list[attr]:
                    # pydaikin human_to_daikin() reverse-map keys are lowercase
                    # (TRANSLATIONS values); device.fan_rate/swing_modes
                    # title-case only for display
                    values[daikin_attr] = value.lower()
                else:
                    raise ServiceValidationError(f"Invalid {attr} value: {value!r}")

            # temperature
            elif attr == ATTR_TEMPERATURE:
                try:
                    # Round to nearest 0.5 to match physical remote behavior
                    value = round(value * 2) / 2
                    values[HA_ATTR_TO_DAIKIN[ATTR_TARGET_TEMPERATURE]] = (
                        format_target_temperature(value)
                    )
                except ValueError:
                    _LOGGER.error("Invalid temperature %s", value)

        if values:
            # Store optimistic values for instant UI feedback
            if ATTR_TEMPERATURE in settings:
                # Round to nearest 0.5 to match physical remote behavior
                self._optimistic_target_temp = round(settings[ATTR_TEMPERATURE] * 2) / 2
            if ATTR_HVAC_MODE in settings:
                self._optimistic_hvac_mode = settings[ATTR_HVAC_MODE]
            if ATTR_FAN_MODE in settings:
                self._optimistic_fan_mode = settings[ATTR_FAN_MODE]
            if ATTR_SWING_MODE in settings:
                self._optimistic_swing_mode = settings[ATTR_SWING_MODE]

            # Record timestamp for staleness detection
            self._optimistic_set_time = time.time()

            # Persistent expected state is recorded by the public handlers via
            # _record_expected_state() BEFORE this method runs (survives
            # mode:restart cancellation). No duplicate write here: it would
            # corrupt the rollback snapshot, and the old unconditional
            # _expected_set_time refresh let fan/temp-only commands extend a
            # stale expected_hvac_mode past its 1h expiry.

            # Trigger immediate UI update
            self.async_write_ha_state()
            # v2.34.0: Yield to event loop so state_changed event is processed
            # This pushes the update to frontend BEFORE blocking device.set()
            await asyncio.sleep(0)

            # v2.37.0: Track ANY command for mode-transition pow bounce suppression
            self._last_any_command_time = time.time()

            try:
                # v2.32.0: SIMPLIFIED - Never pass expected_pow to pydaikin
                # Physical remote detection is handled ONLY via coordinator polling in
                # _handle_coordinator_update().
                # DO NOT update _last_known_pow here — coordinator only.
                # The 45s any-command grace (_last_any_command_time) is the
                # sole command protection window; the old 30s ON/OFF windows
                # were unreachable under it and have been removed (v2.40.0).

                # v2.35.0: Added detailed logging to trace command execution
                _LOGGER.debug(
                    "_set() calling device.set() with values=%s, entity=%s",
                    values, self.entity_id
                )

                # v2.35.1: Use asyncio.shield() to prevent command cancellation
                # When blueprint uses mode:restart, a new trigger cancels the current run.
                # Without shield(), the HTTP request to the AC gets cancelled mid-flight,
                # leaving the AC in an inconsistent state. With shield(), the HTTP request
                # completes even if the automation is cancelled, ensuring the command
                # reaches the device.
                # v2.38.0: Added 60s timeout to prevent hung device.set() from blocking
                # the automation forever.
                # v2.40.0: Explicit task + done-callback. device.set() can
                # legitimately outlive the 45s grace (60s wait_for, BRP084
                # clipping retries) — the device's own pow flip would then land
                # OUTSIDE the grace and fire a false override against our own
                # command. The callback re-stamps _last_any_command_time when
                # the command ACTUALLY completes (success, error, or cancel),
                # so the grace is measured from completion. It also retrieves
                # the orphaned task's exception, silencing asyncio's
                # 'exception was never retrieved'. The pre-call stamp stays —
                # both are required (in-flight window + completion window).
                # Note: hass.async_create_task makes the set task
                # HA-shutdown-cancellable (the old anonymous shield task was
                # untracked); the callback's cancelled() branch handles that.
                set_task = self.hass.async_create_task(
                    self.device.set(values),
                    name=f"daikin_set_{self.entity_id}",
                )

                def _on_set_complete(task: asyncio.Task) -> None:
                    self._last_any_command_time = time.time()
                    if task.cancelled():
                        _LOGGER.warning(
                            "device.set() cancelled before completion. entity=%s values=%s",
                            self.entity_id, values
                        )
                    elif (exc := task.exception()) is not None:
                        _LOGGER.warning(
                            "Shielded device.set() finished with error %r. entity=%s values=%s",
                            exc, self.entity_id, values
                        )

                set_task.add_done_callback(_on_set_complete)

                try:
                    result = await asyncio.wait_for(
                        asyncio.shield(set_task),
                        timeout=60.0
                    )
                except asyncio.TimeoutError:
                    _LOGGER.warning(
                        "_set() timed out after 60s (command may still complete "
                        "in the background). entity=%s, values=%s",
                        self.entity_id, values
                    )
                    raise
                except asyncio.CancelledError:
                    # shield() was cancelled but the inner task continues
                    # Log it but don't clear optimistic state - command is still running
                    _LOGGER.info(
                        "_set() task cancelled but command still executing (shielded). "
                        "entity=%s, values=%s",
                        self.entity_id, values
                    )
                    # Re-raise so HA knows the task was cancelled
                    raise

                _LOGGER.debug(
                    "_set() device.set() completed successfully, entity=%s, result=%s",
                    self.entity_id, result
                )

                # v2.32.0: Removed expected_pow result checking - no longer used
                # Physical remote detection happens via _handle_coordinator_update() only

                # Don't clear optimistic state here - let _handle_coordinator_update() do it
                # when real device state arrives. This keeps UI responsive without flickering.
            except Exception as e:
                # repr(e), not str(e): str(TimeoutError()) is '' which both
                # hid the message and defeated the old substring check.
                _LOGGER.warning(
                    "_set() EXCEPTION: %r. entity=%s, values=%s",
                    e, self.entity_id, values
                )
                # Routine timeouts -> WARNING; everything else -> ERROR.
                # BRP084 wraps its 20s HTTP timeouts in DaikinException with
                # 'timeout' in the message (contract pinned by pydaikin test).
                if isinstance(e, TimeoutError) or (
                    isinstance(e, DaikinException) and "timeout" in str(e).lower()
                ):
                    _LOGGER.warning("Network timeout communicating with device: %r", e)
                else:
                    _LOGGER.error("Error setting device values: %r", e, exc_info=True)

                # Clear optimistic state on failure
                self._optimistic_target_temp = None
                self._optimistic_hvac_mode = None
                self._optimistic_fan_mode = None
                self._optimistic_swing_mode = None
                self._optimistic_set_time = None
                # v2.40.0: A failed MODE command rolls expected state back to
                # the previous successful command's record (keeps the
                # blueprint's expected-vs-actual safety net armed with
                # truthful data). Failed fan/swing/temp-only commands never
                # touched expected state, so nothing to do for them.
                if (
                    ATTR_HVAC_MODE in settings
                    and self._expected_state_snapshot is not None
                ):
                    (
                        self._expected_hvac_mode,
                        self._expected_set_time,
                    ) = self._expected_state_snapshot
                    self._expected_state_snapshot = None
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
        # v2.37.1: Set command time BEFORE _set() to survive mode:restart cancellation
        self._last_any_command_time = time.time()
        # v2.39.0: Set expected state BEFORE _set() to survive mode:restart cancellation
        if ATTR_HVAC_MODE in kwargs:
            self._record_expected_state(kwargs[ATTR_HVAC_MODE])
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
        power_state = self.device.values.get('pow', '1')

        # Check optimistic value first for instant UI feedback
        if self._optimistic_hvac_mode is not None:
            # v2.34.0 FIX: If optimistic is OFF but device shows pow=1 (ON),
            # only trust optimistic during the first 30s command window.
            # After that, device pow=1 takes precedence (command may have failed
            # or user turned AC back on via physical remote)
            if self._optimistic_hvac_mode == HVACMode.OFF:
                if power_state == '1':
                    # Device is ON but we sent OFF - check if stale
                    if self._optimistic_set_time is not None:
                        age = time.time() - self._optimistic_set_time
                        if age < 30:
                            # Still within command processing window - trust optimistic OFF
                            return HVACMode.OFF
                    # Either no timestamp or >30s old - device is actually ON
                    # Don't clear here - let _handle_coordinator_update do it
                    # Return actual device state
                    daikin_mode = self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_HVAC_MODE])[1]
                    return DAIKIN_TO_HA_STATE.get(daikin_mode, HVACMode.HEAT_COOL)
                # Device is OFF (pow=0), optimistic OFF is correct
                return HVACMode.OFF
            # If optimistic is ON mode but device shows pow=0, check timing
            # During command processing (first 30s), trust optimistic
            # After that, device pow=0 takes precedence (physical remote override)
            if power_state == '0':
                if self._optimistic_set_time is not None:
                    age = time.time() - self._optimistic_set_time
                    if age < 30:
                        # Still within command processing window - trust optimistic
                        return self._optimistic_hvac_mode
                # Either no timestamp or >30s old - device is actually off
                # Don't clear here (side effect in property) - let _handle_coordinator_update do it
                return HVACMode.OFF
            # Device is on, return optimistic mode
            return self._optimistic_hvac_mode

        # No optimistic value - return actual device state
        if power_state == '0':
            return HVACMode.OFF

        daikin_mode = self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_HVAC_MODE])[1]
        return DAIKIN_TO_HA_STATE.get(daikin_mode, HVACMode.HEAT_COOL)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        self._last_any_command_time = time.time()
        self._record_expected_state(hvac_mode)
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
        self._last_any_command_time = time.time()
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
        self._last_any_command_time = time.time()
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
        # v2.40.0: Presets arm the 45s grace like every other command path —
        # away mode can change pow and powerful/econo can bounce reported
        # state, which previously fired false physical-remote overrides.
        self._last_any_command_time = time.time()
        try:
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
        except Exception as e:
            _LOGGER.error("Error setting preset mode %s: %s", preset_mode, e, exc_info=True)
            raise
        finally:
            # Re-stamp from completion so slow preset round-trips stay graced
            # (mirror of the _set() done-callback; these calls aren't shielded
            # so a finally suffices).
            self._last_any_command_time = time.time()

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
        """Turn device on, restoring the last coordinator-confirmed mode.

        The old represent()-based restore was dead code: represent('mode')
        returns 'off' whenever pow=0, which is always true during turn_on,
        so it unconditionally fell back to HEAT_COOL.
        Falls back to HEAT_COOL when no active mode was ever confirmed
        (e.g. first turn_on after HA restart with the unit off).
        """
        self._last_any_command_time = time.time()
        target_mode = self._last_active_hvac_mode or HVACMode.HEAT_COOL
        self._record_expected_state(target_mode)
        await self._set({ATTR_HVAC_MODE: target_mode})

    async def async_turn_off(self) -> None:
        """Turn device off."""
        self._last_any_command_time = time.time()
        self._record_expected_state(HVACMode.OFF)
        await self._set({ATTR_HVAC_MODE: HVACMode.OFF})

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # v2.36.0: Detect coordinator recovery (device reboot / network outage / power cut).
        # Only apply grace if the device's pow value actually CHANGED across the outage —
        # benign network blips where state didn't change shouldn't suppress real-remote
        # detection that happens AFTER recovery.
        coordinator_success = self.coordinator.last_update_success
        if coordinator_success and not self._last_coordinator_success:
            current_pow_at_recovery = self.device.values.get('pow', '1')
            if self._last_known_pow != current_pow_at_recovery:
                self._last_coordinator_recovery_time = time.time()
                _LOGGER.info(
                    "Coordinator recovered with pow change (%s -> %s) - applying 60s reconnect grace. entity=%s",
                    self._last_known_pow, current_pow_at_recovery, self.entity_id
                )
            else:
                _LOGGER.debug(
                    "Coordinator recovered, pow unchanged (%s) - no grace needed. entity=%s",
                    self._last_known_pow, self.entity_id
                )
        self._last_coordinator_success = coordinator_success

        # ===== PHYSICAL REMOTE OVERRIDE DETECTION =====
        # Detect when AC turns OFF unexpectedly (user pressed remote)
        # Fire event so blueprint can set Override mode
        current_pow = self.device.values.get('pow', '1')

        # v2.36.0: Startup/reconnect grace period - silently sync _last_known_pow without
        # firing override events. Prevents false positives from:
        # - First 60s after entity init (HA startup, integration reload)
        # - First 60s after coordinator reconnect with pow change (device reboot, network outage)
        _init_age = time.time() - self._entity_init_timestamp
        _recovery_age = (time.time() - self._last_coordinator_recovery_time) if self._last_coordinator_recovery_time else 9999
        in_grace = _init_age < 60 or _recovery_age < 60
        if in_grace:
            if self._last_known_pow != current_pow:
                _grace_reason = "startup" if _init_age < 60 else "reconnect"
                _LOGGER.debug(
                    "%s grace period (init=%.1fs, recovery=%.1fs): syncing _last_known_pow %s -> %s without detection. entity=%s",
                    _grace_reason, _init_age, _recovery_age, self._last_known_pow, current_pow, self.entity_id
                )
                self._last_known_pow = current_pow
            # Fall through to optimistic state handling below (skip override detection)
        elif self._last_any_command_time and (time.time() - self._last_any_command_time) < 45:
            # v2.37.0: Mode transition grace period — suppress override detection for 45s
            # after ANY command. Daikin units bounce pow 1→0→1 during mode transitions
            # (e.g., cool→fan_only), which looks like a physical remote press.
            if self._last_known_pow != current_pow:
                _LOGGER.debug(
                    "Mode transition grace (%.1fs since last command): pow %s -> %s, suppressing detection. entity=%s",
                    time.time() - self._last_any_command_time,
                    self._last_known_pow, current_pow, self.entity_id
                )
                self._last_known_pow = current_pow
        elif self._last_known_pow == '1' and current_pow == '0':
            # AC was ON (coordinator-confirmed), now OFF, and no command was
            # sent within the 45s grace — physical remote press.
            # Debounce: skip if event was fired within last 5 seconds
            # This prevents race condition if _set() and coordinator fire simultaneously
            now = time.time()
            should_fire = True

            if self._last_override_event_time and (now - self._last_override_event_time) < 5:
                _LOGGER.debug(
                    "Skipping duplicate override event (debounce): last event %.1fs ago. entity=%s",
                    now - self._last_override_event_time, self.entity_id
                )
                should_fire = False

            if should_fire:
                # AC was ON, now OFF - user turned it off via physical remote
                _LOGGER.warning(
                    "PHYSICAL REMOTE DETECTED: AC turned OFF unexpectedly. "
                    "entity=%s, was_pow=%s, now_pow=%s",
                    self.entity_id, self._last_known_pow, current_pow
                )
                # Fire event for blueprint to catch
                self.hass.bus.async_fire(
                    "daikin_physical_remote_override",
                    {
                        "entity_id": self.entity_id,
                        # self.name is always None (_attr_name=None with
                        # has_entity_name) — use the device-advertised name
                        "device_name": self.device.values.get('name') or self.entity_id,
                        "action": "turned_off",
                    }
                )
                self._last_override_event_time = now

        # Symmetric detection: AC turned ON unexpectedly (user turned on via physical remote)
        elif self._last_known_pow == '0' and current_pow == '1':
            # AC was OFF (coordinator-confirmed), now ON, and no command was
            # sent within the 45s grace — physical remote press.
            # Debounce: skip if event was fired within last 5 seconds
            now = time.time()
            should_fire = True
            if self._last_override_event_time and (now - self._last_override_event_time) < 5:
                _LOGGER.debug(
                    "Skipping duplicate turn-ON override event (debounce): last event %.1fs ago. entity=%s",
                    now - self._last_override_event_time, self.entity_id
                )
                should_fire = False

            if should_fire:
                # AC was OFF, now ON - user turned it on via physical remote
                _LOGGER.warning(
                    "PHYSICAL REMOTE DETECTED: AC turned ON unexpectedly. "
                    "entity=%s, was_pow=%s, now_pow=%s",
                    self.entity_id, self._last_known_pow, current_pow
                )
                # Fire event for blueprint to catch
                self.hass.bus.async_fire(
                    "daikin_physical_remote_override",
                    {
                        "entity_id": self.entity_id,
                        "device_name": self.device.values.get('name') or self.entity_id,
                        "action": "turned_on",
                    }
                )
                self._last_override_event_time = now

        # Update last known power state
        self._last_known_pow = current_pow

        # v2.40.0: Capture the coordinator-confirmed active mode for turn_on
        # restore. BRP069 auto variants normalize to 'auto'; unmapped daikin
        # modes are deliberately skipped (never stored wrong).
        if current_pow == '1':
            _daikin_mode = self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_HVAC_MODE])[1]
            if _daikin_mode in ('auto-1', 'auto-7'):
                _daikin_mode = 'auto'
            _ha_mode = DAIKIN_TO_HA_STATE.get(_daikin_mode)
            if _ha_mode is not None and _ha_mode is not HVACMode.OFF:
                self._last_active_hvac_mode = _ha_mode

        # ===== END PHYSICAL REMOTE DETECTION =====

        # v2.36.0: Clear stale persistent expected state (>1 hour old)
        if self._expected_set_time is not None:
            if (time.time() - self._expected_set_time) > 3600:
                self._expected_hvac_mode = None
                self._expected_set_time = None

        # Check if optimistic values are stale (>30 seconds old)
        # This prevents stuck optimistic state from manual changes or failed commands
        optimistic_timeout = 30  # seconds
        is_stale = False

        if self._optimistic_set_time is not None:
            age = time.time() - self._optimistic_set_time
            is_stale = age > optimistic_timeout
            if is_stale:
                _LOGGER.debug(
                    "Optimistic state is stale (%.1fs old), clearing unconditionally",
                    age
                )

        # Clear optimistic values if they match device state OR are stale
        if self._optimistic_target_temp is not None:
            if is_stale or (self.device.target_temperature is not None and abs(self.device.target_temperature - self._optimistic_target_temp) < 0.1):
                self._optimistic_target_temp = None

        if self._optimistic_hvac_mode is not None:
            power_state = self.device.values.get('pow', '1')
            # If device is OFF and optimistic was an ON mode, clear it (stale after timeout)
            if power_state == '0' and self._optimistic_hvac_mode != HVACMode.OFF:
                if is_stale:
                    self._optimistic_hvac_mode = None
            # v2.34.0 FIX: If device is ON but optimistic was OFF, clear it if stale
            # This handles the case where OFF command failed or user turned AC back on
            elif power_state == '1' and self._optimistic_hvac_mode == HVACMode.OFF:
                if is_stale:
                    _LOGGER.debug(
                        "Clearing stale optimistic OFF - device is ON (pow=1). entity=%s",
                        self.entity_id
                    )
                    self._optimistic_hvac_mode = None
            else:
                # Device is ON or optimistic is OFF - normal comparison
                daikin_mode = self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_HVAC_MODE])[1]
                actual_mode = DAIKIN_TO_HA_STATE.get(daikin_mode, HVACMode.HEAT_COOL)
                # Also treat OFF state match: if device pow=0 and optimistic=OFF, clear it
                if power_state == '0' and self._optimistic_hvac_mode == HVACMode.OFF:
                    self._optimistic_hvac_mode = None
                elif is_stale or actual_mode == self._optimistic_hvac_mode:
                    self._optimistic_hvac_mode = None

        if self._optimistic_fan_mode is not None:
            actual_fan = self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_FAN_MODE])[1].title()
            if is_stale or actual_fan == self._optimistic_fan_mode:
                self._optimistic_fan_mode = None

        if self._optimistic_swing_mode is not None:
            actual_swing = self.device.represent(HA_ATTR_TO_DAIKIN[ATTR_SWING_MODE])[1].title()
            if is_stale or actual_swing == self._optimistic_swing_mode:
                self._optimistic_swing_mode = None

        # Clear timestamp if all optimistic values are gone
        if (
            self._optimistic_target_temp is None
            and self._optimistic_hvac_mode is None
            and self._optimistic_fan_mode is None
            and self._optimistic_swing_mode is None
        ):
            self._optimistic_set_time = None

        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for blueprint override detection.

        These attributes allow the Ultimate Climate Control blueprint to detect
        manual overrides by comparing expected state (what automation commanded)
        vs actual state (what the device reports).
        """
        # v2.36.0: Prefer persistent expected state over optimistic state for attributes.
        # Optimistic clears after 30s, but persistent expected stays for up to 1 hour,
        # keeping blueprint override detection active well after last command.

        # Expected HVAC mode: persistent first, then optimistic fallback
        expected_hvac = self._expected_hvac_mode
        if expected_hvac is None and self._optimistic_hvac_mode is not None:
            expected_hvac = getattr(
                self._optimistic_hvac_mode, 'value', str(self._optimistic_hvac_mode)
            )

        # Last command time: persistent first, then optimistic fallback
        last_cmd_time = None
        if self._expected_set_time is not None:
            last_cmd_time = dt_util.utc_from_timestamp(self._expected_set_time).isoformat()
        elif self._optimistic_set_time is not None:
            last_cmd_time = dt_util.utc_from_timestamp(self._optimistic_set_time).isoformat()

        # Get entity init time for startup grace period
        entity_init_time = None
        if hasattr(self, '_entity_init_time'):
            entity_init_time = self._entity_init_time

        return {
            "expected_hvac_mode": expected_hvac,
            "expected_temperature": self._optimistic_target_temp,
            "expected_fan_mode": self._optimistic_fan_mode,
            "expected_swing_mode": self._optimistic_swing_mode,
            "last_command_time": last_cmd_time,
            "entity_init_time": entity_init_time,
            "device_type": type(self.device).__name__,
        }
