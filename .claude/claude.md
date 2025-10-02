# Home Assistant Daikin Integration - Optimized

## Project Structure

This repository is part of a two-repository system for the Daikin Home Assistant integration:

### Repository 1: Home Assistant Daikin Integration (this repo)
**Repository**: https://github.com/Chris971991/homeassistant-daikin-optimized
- Home Assistant integration for Daikin AC units
- Provides climate entities, sensors, and switches
- Optimized with optimistic updates for instant UI response

### Repository 2: pydaikin Library
**Repository**: https://github.com/Chris971991/pydaikin-2.8.0
- Core library for communicating with Daikin AC units
- Supports multiple firmware versions (BRP069, BRP072C, BRP084/2.8.0, AirBase, SkyFi)
- Used by this integration

## Working on Both Repositories Together

When making changes to the Daikin integration, you often need to edit **both repositories in conjunction**:

1. **pydaikin changes** (pydaikin-2.8.0 repo):
   - Add/modify device communication protocols
   - Add new properties or methods
   - Fix parsing issues
   - Example: Adding `inside_temperature` property for HA compatibility

2. **HA integration changes** (this repo):
   - Use the new pydaikin features
   - Update UI/UX
   - Add optimizations
   - Example: Using `device.inside_temperature` in climate entity

### Typical Workflow

```bash
# Working on pydaikin
cd C:\Users\Chris\Documents\pydaikin-2.8.0
# Make changes to pydaikin/daikin_brp084.py or other files
git add .
git commit -m "Add new feature"
git push

# Working on HA integration
cd C:\Users\Chris\Documents\homeassistant-daikin-optimized
# Make changes to custom_components/daikin/climate.py or other files
git add .
git commit -m "Use new pydaikin feature"
git push
```

### Version Management

- **pydaikin version**: Update in pydaikin's `pyproject.toml`
- **HA integration requirement**: Update in `custom_components/daikin/manifest.json`

When pydaikin adds features:
1. Bump pydaikin version (e.g., 2.16.1 → 2.17.0)
2. Update this integration's manifest.json to require new version

## Recent Optimizations

### Optimistic State Updates
- Added instant UI feedback for all commands
- UI updates immediately, actual device state confirmed via polling
- Response time: 1-4s → <0.1s

### Removed Redundant Refreshes
- Removed `coordinator.async_refresh()` after every command
- Reduced HTTP requests per command by 50%
- Regular 60-second polling handles state synchronization

### Firmware 2.8.0 Support
- Full support for BRP084 firmware via pydaikin
- Auto-detection of firmware version
- Unified integration for all firmware types

## File Structure

```
custom_components/daikin/
├── __init__.py           # Integration setup, coordinator
├── climate.py            # Climate entity (main optimizations here)
├── config_flow.py        # Configuration UI
├── const.py              # Constants
├── coordinator.py        # Data update coordinator
├── entity.py             # Base entity class
├── manifest.json         # Integration metadata
├── sensor.py             # Sensor entities
├── strings.json          # Translations
└── switch.py             # Switch entities
```

## Testing

Test with multiple firmware versions:
- ✅ BRP069 (older firmware)
- ✅ BRP084 (firmware 2.8.0)
- ✅ All HVAC modes
- ✅ All fan speeds
- ✅ All swing modes
- ✅ Temperature changes

### Local Testing

1. Copy to Home Assistant:
   ```bash
   cp -r custom_components/daikin /config/custom_components/
   ```

2. Restart Home Assistant

3. Check logs for errors

## Pull Request Plan

This repository is a staging area for changes to submit to Home Assistant core.

**Target Repository**: https://github.com/home-assistant/core

**Files to Submit**:
- Only `homeassistant/components/daikin/climate.py` (main changes)
- Other files unchanged from upstream

**See**: `PULL_REQUEST_CHECKLIST.md` for detailed PR instructions

## Performance Metrics

| Operation | Before | After | Improvement |
|-----------|--------|-------|-------------|
| Startup | 3-6s | 2-3s | 2-3x faster |
| Commands | 1-4s | <0.1s | 10-40x faster |
| HTTP Requests | 2 per command | 1 per command | 50% reduction |

## Supported Devices

- ✅ 2x AC units with old firmware (BRP069)
- ✅ 1x AC unit with firmware 2.8.0 (BRP084)
- ✅ Auto-detection of firmware version
- ✅ Single unified integration

## Important Notes

- **Optimistic updates** trade immediate accuracy for perceived responsiveness
- Actual device state confirmed every 60 seconds via coordinator
- Failed commands revert UI to actual state
- Net result: Much better UX with minimal trade-offs

## Local Paths

- HA integration: `C:\Users\Chris\Documents\homeassistant-daikin-optimized`
- pydaikin: `C:\Users\Chris\Documents\pydaikin-2.8.0`
- Home Assistant: `http://192.168.50.45:8123/`
- AC IPs:
  - 192.168.50.47 (firmware 2.8.0 - Living Room)
  - 192.168.50.57 (old firmware)
  - 192.168.50.216 (old firmware)

## Related Documentation

- `PR_DESCRIPTION.md` - PR description template
- `PULL_REQUEST_CHECKLIST.md` - Step-by-step PR guide
- `OPTIMISTIC_UPDATES.md` - Technical details
- `ALL_IN_ONE_SOLUTION.md` - How it all works together
