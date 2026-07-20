## v1.1.0 (2026-07-20)

### Feat

- **build**: add app icon for macOS and Windows
- **ui**: add header with logo + app smoke test

## v1.0.3 (2026-03-05)

### Fix

- add ad-hoc codesign to macOS builds to prevent Gatekeeper 'damaged' error

### Refactor

- split release workflow into bump.yml + release.yml

## v1.0.2 (2026-03-05)

### Fix

- replace GNU timeout with portable bash pattern for macOS smoke test
- skip numba on macOS Intel (no llvmlite wheel for py3.13 x86_64)
- replace deprecated macos-13 runner with macos-15-intel for Intel x64 builds

## v1.0.1 (2026-03-04)
