# Pull Request Checklist

## Repository Ready for PR

✅ **GitHub Repository**: https://github.com/Chris971991/homeassistant-daikin-optimized
✅ **pydaikin Repository**: https://github.com/Chris971991/pydaikin-2.8.0

## Files Changed

### Home Assistant Integration
- `custom_components/daikin/climate.py` - Main changes
  - Added optimistic state updates
  - Removed redundant coordinator refresh calls
  - Added `_handle_coordinator_update()` to clear optimistic state

### pydaikin Library
- `pydaikin/daikin_brp084.py`
  - Added `inside_temperature` property
  - Added `target_temperature` property
  - Added `outside_temperature` property
  - Version bumped to 2.17.0

## PR Submission Steps

### 1. Fork home-assistant/core Repository
```bash
# On GitHub, fork: https://github.com/home-assistant/core
```

### 2. Clone Your Fork
```bash
git clone https://github.com/Chris971991/core.git
cd core
```

### 3. Create Feature Branch
```bash
git checkout -b daikin-optimistic-updates
```

### 4. Copy Changes
Copy only these files from `homeassistant-daikin-optimized` to `core`:
- `homeassistant/components/daikin/climate.py`

**DO NOT copy**:
- manifest.json (keep original version requirement)
- Other files (unchanged)

### 5. Apply Changes Manually
The changes in `climate.py` are:
1. Added optimistic state variables in `__init__()`
2. Modified `_set()` method to store optimistic state
3. Removed all `coordinator.async_refresh()` calls
4. Added `_handle_coordinator_update()` method

### 6. Test
```bash
# Run Home Assistant's test suite
pytest tests/components/daikin/
```

### 7. Commit
```bash
git add homeassistant/components/daikin/climate.py
git commit -m "Add optimistic updates to Daikin integration

- Add optimistic state for instant UI feedback
- Remove redundant coordinator refresh after commands
- Improves response time from 1-4s to <0.1s
"
```

### 8. Push and Create PR
```bash
git push origin daikin-optimistic-updates
# Then create PR on GitHub
```

## PR Description Template

Use the content from `PR_DESCRIPTION.md` in this repository.

## Important Notes

1. **pydaikin Changes**: The pydaikin changes should be submitted as a separate PR to the pydaikin repository (https://github.com/fredrike/pydaikin)

2. **Version Requirement**: Keep `requirements: ["pydaikin>=2.16.0"]` in manifest.json for the HA PR. The 2.17.0 properties are optional/nice-to-have.

3. **Testing**: Make sure to test with both old firmware and firmware 2.8.0 devices

4. **Code Style**: Run `black` and `isort` before committing

## Testing Commands

```bash
# Format code
black homeassistant/components/daikin/
isort homeassistant/components/daikin/

# Run tests
pytest tests/components/daikin/

# Type check
mypy homeassistant/components/daikin/
```

## Success Criteria

✅ All tests pass
✅ Code follows Home Assistant style guide
✅ No breaking changes
✅ Performance improvement demonstrated
✅ Works with multiple firmware versions

---

**Current Status**: Ready for PR submission
**Repository**: https://github.com/Chris971991/homeassistant-daikin-optimized
