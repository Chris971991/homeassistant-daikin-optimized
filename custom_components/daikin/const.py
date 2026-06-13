"""Constants for Daikin."""

DOMAIN = "daikin"

ATTR_TARGET_TEMPERATURE = "target_temperature"
ATTR_INSIDE_TEMPERATURE = "inside_temperature"
ATTR_OUTSIDE_TEMPERATURE = "outside_temperature"

ATTR_TARGET_HUMIDITY = "target_humidity"
ATTR_HUMIDITY = "humidity"

ATTR_COMPRESSOR_FREQUENCY = "compressor_frequency"

ATTR_ENERGY_TODAY = "energy_today"
ATTR_COOL_ENERGY = "cool_energy"
ATTR_HEAT_ENERGY = "heat_energy"

ATTR_TOTAL_POWER = "total_power"
ATTR_TOTAL_ENERGY_TODAY = "total_energy_today"

ATTR_STATE_ON = "on"
ATTR_STATE_OFF = "off"

KEY_MAC = "mac"
KEY_IP = "ip"

TIMEOUT = 60

# Overall ceiling for one coordinator poll (seconds).
# 90s: above pydaikin's worst-case tenacity budget (3x20s + backoff ~= 62s) and
# above 4 serialized 20s requests on MAX_CONCURRENT_REQUESTS=1 BRP069 devices
# once energy resources return. Still bounds hung polls — DataUpdateCoordinator
# debounces overlapping refreshes, so a >interval poll does not pile up.
COORDINATOR_UPDATE_TIMEOUT = 90

# Default polling interval for state updates (seconds)
# Reduced to 10s for better responsiveness to manual remote changes
# Can be overridden via options flow in the future
DEFAULT_UPDATE_INTERVAL = 10
