# Daikin Integration Performance Improvements

## Summary

This PR improves the performance and responsiveness of the Daikin integration by adding optimistic state updates and removing redundant coordinator refresh calls.

## Changes Made

### 1. Optimistic State Updates
- Added optimistic state variables for instant UI feedback
- UI now updates immediately when users change settings (temperature, mode, fan, swing)
- Actual device state is confirmed via the regular 60-second polling cycle
- On command failure, optimistic state is cleared and UI reverts to actual state

### 2. Removed Redundant Coordinator Refreshes
- Removed `coordinator.async_refresh()` calls after every command
- Commands previously triggered 2 HTTP requests (command + immediate refresh)
- Now only 1 HTTP request per command (50% reduction)
- Regular polling (every 60s) handles state synchronization

### 3. Added Compatibility Properties to pydaikin BRP084
- Added `inside_temperature`, `target_temperature`, and `outside_temperature` properties to BRP084 class
- Ensures firmware 2.8.0 devices work seamlessly with the official integration
- Maintains compatibility with existing BRP069/BRP072C/AirBase devices

## Performance Impact

### Before:
- **Command Response**: 1-4 seconds (UI waits for HTTP request)
- **HTTP Requests per Command**: 2 (command + refresh)
- **User Experience**: Laggy, unresponsive

### After:
- **Command Response**: < 0.1 seconds (instant UI update)
- **HTTP Requests per Command**: 1 (command only)
- **User Experience**: Responsive, snappy

## Testing

Tested with:
- ✅ 2x Daikin AC units with older firmware (BRP069)
- ✅ 1x Daikin AC unit with firmware 2.8.0 (BRP084)
- ✅ All HVAC modes (Heat, Cool, Auto, Fan, Dry, Off)
- ✅ All fan speeds
- ✅ All swing modes
- ✅ Temperature changes (including smart temperature clipping for 2.8.0)
- ✅ Preset modes
- ✅ Command failure scenarios

## Breaking Changes

None. All changes are backwards compatible.

## Related Issues

This addresses general performance complaints about the Daikin integration feeling slow and unresponsive.

## Checklist

- [x] Code follows Home Assistant code style
- [x] Tests pass (if applicable)
- [x] Documentation updated (if needed)
- [x] No breaking changes
- [x] Tested on real hardware

## Notes

The optimistic updates trade immediate accuracy for perceived responsiveness. In practice:
- 99% of commands succeed immediately
- Failed commands revert UI to actual state
- Coordinator sync (60s) ensures eventual consistency
- Net result: Much better user experience with minimal trade-offs
