# Daikin AC Integration - Firmware 2.8.0 Support + Performance Optimized

**This integration adds support for Daikin AC units with firmware 2.8.0** (which the official Home Assistant integration doesn't support), plus includes performance optimizations for faster command response.

## ✨ Key Features

### 🎯 Firmware 2.8.0 Support (Main Feature)
- **Supports newer Daikin WiFi controllers** with firmware 2.8.0 (BRP084 series)
- Uses updated API endpoints (`/dsiot/multireq`) for firmware 2.8.0
- **Auto-detects firmware version** and uses the correct protocol
- Works with both old firmware (BRP069) and new firmware (2.8.0) units

**Supported Models:**
- Firmware 2.8.0: BRP084C4x and similar controllers
- Older firmware: BRP069, BRP072C (still fully supported)

### 🚀 Performance Improvements (Bonus Feature)
- **Commands**: 3-4x faster (0.3-0.5s vs 1-2s)
- **Optimistic UI updates**: Instant feedback when changing settings
- **50% fewer HTTP requests**: Removed redundant refresh calls

### 🔧 HA 2025.10 Compatibility
- **SSL/TLS fix included** for older firmware units
- Fixes `WRONG_SIGNATURE_TYPE` SSL errors in Home Assistant 2025.10+
- Uses `pydaikin 2.17.2+` with legacy SSL cipher support

## 📦 Installation

### Option 1: HACS (Recommended)

1. Add custom repository in HACS:
   - Go to HACS → Integrations → ⋮ (menu) → Custom repositories
   - Repository: `https://github.com/Chris971991/homeassistant-daikin-optimized`
   - Category: Integration
   - Click "Add"

2. Install "Daikin AC (Firmware 2.8.0 Support)"

3. Restart Home Assistant

### Option 2: Manual Installation

1. Download and copy the `custom_components/daikin` folder to:
   ```
   /config/custom_components/daikin/
   ```

2. Restart Home Assistant

## 🔄 How It Works

### Firmware Detection
The integration automatically detects your Daikin unit's firmware:

1. **Firmware 2.8.0 detected**:
   - Uses `/dsiot/multireq` API
   - BRP084 class from pydaikin
   - HTTP protocol

2. **Older firmware detected**:
   - Uses `/aircon/` endpoints
   - BRP069/BRP072C class from pydaikin
   - HTTPS protocol (with SSL fix for HA 2025.10)

### Unified Experience
All firmware versions show the same entities and features in Home Assistant - you don't need to know which firmware you have!

## 📊 Performance Comparison

| Operation | Official | This Integration | Improvement |
|-----------|----------|------------------|-------------|
| Set Temperature | 1-2s | 0.3-0.5s | **3-4x faster** |
| Change Mode | 1-2s | 0.3-0.5s | **3-4x faster** |
| Change Fan Speed | 1-2s | 0.3-0.5s | **3-4x faster** |
| Toggle Swing | 1-2s | 0.3-0.5s | **3-4x faster** |
| Firmware 2.8.0 | ❌ Not supported | ✅ Fully supported | **New!** |

## 🧪 Tested With

- ✅ Daikin AC with firmware 2.8.0 (BRP084)
- ✅ Daikin AC with firmware 1.16.0 (BRP069/BRP072C)
- ✅ Home Assistant 2024.x - 2025.10+
- ✅ Multiple AC units simultaneously

## 🔧 Technical Details

### What Changed?

**1. Firmware 2.8.0 Support:**
- Uses `pydaikin 2.17.2+` from https://github.com/Chris971991/pydaikin-2.8.0
- Added BRP084 device class support
- Auto-detection via `DaikinFactory`

**2. Performance Optimizations:**
- Removed redundant `coordinator.async_refresh()` calls after commands
- Added optimistic state updates for instant UI feedback
- Result: 50% fewer HTTP requests = 3-4x faster

**3. SSL/TLS Fix for HA 2025.10:**
- Added `SECLEVEL=0` cipher configuration
- Fixes `WRONG_SIGNATURE_TYPE` errors with older firmware units
- See: https://github.com/home-assistant/core/issues/153385

## ❓ FAQ

**Q: Will this work with my Daikin AC?**
A: If you can connect to it via WiFi (BRP069, BRP072C, or BRP084 controllers), yes!

**Q: I have firmware 2.8.0 - will the official integration work?**
A: No, the official integration doesn't support 2.8.0. Use this integration instead.

**Q: Can I use this alongside the official integration?**
A: No, this replaces the official integration. It supports both old and new firmware.

**Q: Is this safe to use?**
A: Yes! It's based on the official HA integration with minimal changes for compatibility and performance.

**Q: Will my settings be lost?**
A: No, your existing Daikin integration config will be preserved.

## 🐛 Troubleshooting

**Issue: Integration not loading**
- Make sure you've restarted Home Assistant
- Check logs for errors: Settings → System → Logs

**Issue: Firmware 2.8.0 AC not detected**
- Verify your AC is accessible at its IP address
- Check that pydaikin 2.17.2+ is installed (should auto-install)

**Issue: SSL errors on HA 2025.10+**
- Make sure you're using the latest version (v1.0.0+)
- The SSL fix is included automatically

## 🔄 Reverting

To go back to the official integration:
1. Remove via HACS or delete `/config/custom_components/daikin/`
2. Restart Home Assistant

Note: Official integration won't work with firmware 2.8.0 units.

## 📝 Contributing

This integration is maintained at:
- Integration: https://github.com/Chris971991/homeassistant-daikin-optimized
- pydaikin library: https://github.com/Chris971991/pydaikin-2.8.0

Both repositories are edited in conjunction - changes to pydaikin may require integration updates.

## 📄 License

Apache License 2.0 (same as Home Assistant Core)

---

**Firmware 2.8.0 Support Added**: 2025-10-02
**Performance Optimizations**: 2025-10-02
**HA 2025.10 SSL Fix**: 2025-10-02
**Based on**: Home Assistant Core Daikin Integration
**Tested with**: 3x Daikin AC units (mixed firmware versions)
