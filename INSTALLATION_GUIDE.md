# Installation Guide - Optimized Daikin Integration

## 🎯 Quick Start

### Step 1: Locate Your Home Assistant Config Folder

Your Home Assistant configuration is typically at one of these locations:

**Windows (Docker/VM)**:
- Check where you mounted the config volume

**Linux**:
- `/config/` (if using Home Assistant OS)
- `~/.homeassistant/` (if using core installation)

**Finding it**:
1. Go to Home Assistant UI: http://192.168.50.45:8123/
2. Settings → System → Storage
3. Look for "Configuration path"

### Step 2: Copy the Optimized Integration

**From this PC**:
```
C:\Users\Chris\Documents\homeassistant-daikin-optimized\custom_components\daikin
```

**To your Home Assistant config folder**:
```
/config/custom_components/daikin
```

### Step 3: Full Installation Steps

#### Option A: Using File Share (Easiest)

1. **Enable Samba** on your Home Assistant:
   - Settings → Add-ons → Add-on Store
   - Search for "Samba share"
   - Install and start it

2. **Access from Windows**:
   - Open File Explorer
   - Go to: `\\192.168.50.45\config`
   - Create folder: `custom_components` (if it doesn't exist)
   - Copy the entire `daikin` folder from:
     `C:\Users\Chris\Documents\homeassistant-daikin-optimized\custom_components\daikin`
   - To: `\\192.168.50.45\config\custom_components\daikin`

3. **Restart Home Assistant**:
   - Settings → System → Restart

#### Option B: Using SSH/Terminal

1. **Enable SSH** on Home Assistant:
   - Settings → Add-ons → Add-on Store
   - Search for "Terminal & SSH"
   - Install and start it

2. **Connect via SSH** from Windows PowerShell:
   ```powershell
   ssh root@192.168.50.45
   ```

3. **Create directory and copy files**:
   ```bash
   mkdir -p /config/custom_components/daikin
   ```

4. **Copy files from Windows to Home Assistant**:
   - Use WinSCP or FileZilla to transfer files
   - Or use the File Editor add-on to create each file manually

#### Option C: Manual File Creation (If SSH/Samba not available)

1. Install **File Editor** add-on in Home Assistant
2. Create folder structure: `/config/custom_components/daikin/`
3. Copy each file's content from this folder to Home Assistant one by one

### Step 4: Verify Installation

After restarting Home Assistant:

1. Go to Settings → Devices & Services
2. Look for "Daikin AC (Performance Optimized)"
3. Your existing Daikin devices should now use the optimized version

### Step 5: Test Performance

1. **Test Command Speed**:
   - Change temperature on one of your 2 official Daikin ACs
   - Should respond in < 0.5 seconds (vs 1-2 seconds before)

2. **Test All Functions**:
   - Temperature changes
   - Mode changes (Heat/Cool/Auto/Fan/Dry)
   - Fan speed changes
   - Swing mode changes
   - Turn on/off

3. **Monitor for Issues**:
   - Settings → System → Logs
   - Look for any errors related to "daikin"

## 🔍 Troubleshooting

### Issue: "Integration not loading"

**Solution**:
1. Check file permissions (should match other folders)
2. Verify all files are present (10 files total)
3. Check logs for specific errors

### Issue: "Still seeing slow performance"

**Solution**:
1. Make sure you restarted Home Assistant
2. Verify the integration name shows "(Performance Optimized)"
3. Clear browser cache and refresh UI

### Issue: "State updates delayed"

**This is normal!**
- Commands execute fast (< 0.5s)
- State updates happen every 60 seconds via polling
- Home Assistant shows "optimistic" updates immediately

## 📂 Expected File Structure

After installation, you should have:

```
/config/
└── custom_components/
    └── daikin/
        ├── __init__.py
        ├── climate.py
        ├── config_flow.py
        ├── const.py
        ├── coordinator.py
        ├── entity.py
        ├── manifest.json
        ├── sensor.py
        ├── strings.json
        └── switch.py
```

## 🔄 Reverting to Official Integration

If you want to go back to the official integration:

1. Delete `/config/custom_components/daikin/`
2. Restart Home Assistant
3. The built-in integration will take over

## ✅ Success Criteria

You'll know it's working when:

✅ Integration shows as "Daikin AC (Performance Optimized)"
✅ Temperature changes respond in < 0.5 seconds
✅ Mode/fan/swing changes are instant
✅ No errors in logs
✅ All 2 Daikin ACs still work normally

## 📞 Need Help?

If you run into issues:
1. Check Home Assistant logs (Settings → System → Logs)
2. Verify file structure matches above
3. Make sure Home Assistant was restarted after installation

---

**Your Setup**:
- Home Assistant: http://192.168.50.45:8123/
- Devices: 2x Daikin AC (official integration) + 1x Daikin AC (custom daikin_2_8_0)
- Source Files: `C:\Users\Chris\Documents\homeassistant-daikin-optimized\custom_components\daikin`
