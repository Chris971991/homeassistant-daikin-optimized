# Troubleshooting Slow Performance

## Step 1: Verify Custom Integration is Loaded

### Check Integration Name
1. Go to Settings → Devices & Services
2. Find your Daikin integration
3. It should say **"Daikin AC (Performance Optimized)"**
4. If it just says "Daikin AC", the custom version isn't loading

### Check Logs for Diagnostic Message
1. Go to Settings → System → Logs
2. Change a fan mode or temperature
3. Look for: `🚀 OPTIMIZED VERSION - Setting: ...`
4. If you DON'T see this, the custom integration isn't being used

## Step 2: Verify File Installation

Check that files exist:
```
/config/custom_components/daikin/__init__.py
/config/custom_components/daikin/climate.py
/config/custom_components/daikin/manifest.json
... (all 10 files)
```

## Step 3: Force Integration Reload

1. Settings → Devices & Services
2. Find "Daikin AC"
3. Click the 3 dots → Reload
4. OR: Restart Home Assistant completely

## Step 4: Test Network Latency

The slowness might be your network or the Daikin devices themselves!

**Test this:**
1. Open PowerShell/Terminal
2. Ping your Daikin AC:
   ```
   ping [YOUR_DAIKIN_IP]
   ```
3. Should be < 10ms
4. If > 50ms, that's your problem (Wi-Fi/network issue)

## Step 5: Check Daikin Device Response Time

The Daikin units themselves might be slow! Test:

1. Use curl to send a command directly:
   ```bash
   curl "http://[DAIKIN_IP]/aircon/set_control_info?pow=1&mode=3&stemp=22&f_rate=A"
   ```
2. Time how long it takes
3. If > 1 second, the Daikin device itself is slow

## Common Issues

### Issue: Integration Not Loading

**Symptom**: Still see "Daikin AC" not "Daikin AC (Performance Optimized)"

**Solutions**:
1. Make sure folder is `/config/custom_components/daikin` (not `daikin_optimized`)
2. Check file permissions match other folders
3. Restart Home Assistant (not just reload)
4. Check Home Assistant logs for integration load errors

### Issue: Commands Still Slow (1-2 seconds)

**Symptom**: Fan changes take 3 tries, temperature takes forever

**Possible Causes**:
1. **Network latency** - Daikin on slow Wi-Fi
2. **Device itself slow** - Older firmware
3. **Integration not actually loaded** - Still using built-in version

**Solutions**:
1. Move Daikin closer to Wi-Fi router or use Ethernet
2. Check device firmware version
3. Verify custom integration is loaded (see Step 1)

### Issue: Fan Mode Needs 3 Tries

**This is strange!** This suggests:
1. Commands are being sent but rejected
2. Network packets are being dropped
3. Daikin device is overwhelmed

**Debug this**:
1. Check Home Assistant logs during fan change
2. Look for errors or warnings
3. Check if you see multiple "Setting: fan_mode" messages

## Step 6: Enable Debug Logging

Add to `/config/configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.daikin: debug
    pydaikin: debug
```

Restart, then check logs after sending a command.

## Expected Behavior After Optimization

✅ **Command Response**: UI updates instantly (optimistic)
✅ **HTTP Request**: Completes in < 500ms
✅ **State Confirmation**: Within 60 seconds (next poll)
❌ **NOT expected**: Still waiting 1-2 seconds after clicking

## Still Slow? Let's Dig Deeper

If you've verified the custom integration is loaded and it's still slow, the problem is likely:

1. **Network/Wi-Fi**: Daikin devices on poor connection
2. **Device firmware**: Old/buggy firmware on Daikin
3. **Home Assistant overload**: Too many integrations/slow system

**Next steps**:
- Share Home Assistant logs
- Test direct curl commands to Daikin
- Check Wi-Fi signal strength of Daikin units
