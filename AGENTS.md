# Agent Instructions — MultiChannelWavMixer

This file provides guidance for AI coding agents (GitHub Copilot, Codex, etc.) working on this repository.

---

## Project overview

MultiChannelWavMixer is a cross-platform desktop GUI application (customtkinter / Tkinter) for downmixing multichannel WAV files to stereo. It targets **RME Durec** recorder output and reads embedded iXML metadata.

Key characteristics:
- Pure Python, no C extensions written by the project itself
- GUI code lives entirely in `MultiChannelWavMixer.py`; all audio logic is in `mixer_utils.py`
- Distributed as a self-contained native app via PyInstaller (`.app` on macOS, folder + `.exe` on Windows)
- Managed with [uv](https://docs.astral.sh/uv/); never use bare `pip` or `python` commands

---

## Repository layout

```
MultiChannelWavMixer.py      # GUI layer — customtkinter, no business logic
mixer_utils.py               # Pure audio logic — no GUI imports, fully unit-tested
MultiChannelWavMixer.spec    # PyInstaller spec (cross-platform)
pyi_rth_env.py               # PyInstaller runtime hook
build.sh                     # Local build helper (wraps pyinstaller spec)
MixConf.json                 # Persisted channel configuration (runtime artefact)
pyproject.toml               # Dependencies, tool config, commitizen version source
uv.lock                      # Locked dependency graph — always commit alongside pyproject.toml changes
requirements.txt             # Legacy reference only — do not modify
.github/
  workflows/
    ci.yml                   # PR checks: lint → tests → build matrix + smoke test
    bump.yml                 # Merge to Main: commitizen version bump + tag push
    release.yml              # Tag push: build matrix + smoke test + GitHub Release
tests/
  test_mixer_utils.py        # Unit tests (GUI-free)
doc/                         # Screenshots / assets
```

---

## Architecture rules

1. **`mixer_utils.py` must remain GUI-free.** No `tkinter`, `customtkinter`, or display imports. All audio processing, file I/O, and playback logic belongs here.
2. **`MultiChannelWavMixer.py` must not contain reusable logic.** It wires the GUI to `mixer_utils` functions only.
3. **All new `mixer_utils` functions must have unit tests** in `tests/test_mixer_utils.py`. Tests run without a display and must pass on all three platforms.

---

## Development environment

```sh
uv sync --all-groups      # install all deps including dev (ruff, pytest, pyinstaller, commitizen)
uv run pytest -v          # run the test suite
uv run ruff check .       # lint
uv run ruff format .      # format
bash build.sh --clean     # local PyInstaller build (macOS .app)
```

Python version is pinned to **3.13** via `.python-version` and `pyproject.toml`.

### Dependency changes

When adding or removing dependencies:
1. Edit `pyproject.toml` (`[project].dependencies` for runtime, `[dependency-groups].dev` for dev tools).
2. Run `uv lock` to regenerate `uv.lock`.
3. Commit **both** `pyproject.toml` and `uv.lock` together.

> **macOS Intel (x86_64) constraint**: `llvmlite` (a `numba` dependency) has no pre-built wheel for Python 3.13 on macOS x86_64. A `[tool.uv.override-dependencies]` entry in `pyproject.toml` conditionally skips `numba` on that platform. Do not remove this override.

---

## Pre-commit checklist

**Always run all three of these commands and confirm they pass before every `git commit`:**

```sh
uv run ruff format .      # auto-format — re-stage any files it changes
uv run ruff check .       # lint — must report "All checks passed!"
uv run pytest --tb=short -q  # tests — must report 0 failures, 0 errors
```

Do not commit if any of these steps fails. Fix the issue first, then re-run all three.

---

## Git workflow

```
dev  →  Pull Request  →  Main
         (CI checks)      (bump.yml tags → release.yml builds & releases)
```

- All work is done on `dev` (or a feature branch off `dev`).
- **Never commit directly to `Main`.**
- Merge to `Main` only via a reviewed Pull Request.
- The CI pipeline must be green before merging.

### Commit message convention (Conventional Commits)

| Prefix | Bump | When to use |
|---|---|---|
| `fix:` | patch | Bug fixes |
| `feat:` | minor | New user-visible features |
| `feat!:` / `BREAKING CHANGE:` | major | Breaking API or behaviour change |
| `refactor:` | none | Code restructuring with no behaviour change |
| `chore:` | none | Maintenance, dependency updates |
| `ci:` | none | Workflow / pipeline changes |
| `docs:` | none | Documentation only |
| `test:` | none | Tests only |

Commitizen reads these prefixes automatically on every merge to `Main` to decide whether and how to bump the version. Getting the prefix right is important.

---

## CI/CD pipeline

### `ci.yml` — runs on every PR to `Main`

1. **Lint** (`ubuntu-latest`) — `ruff check` and `ruff format --check`
2. **Test** (`macos-latest`, needs lint) — `pytest` with JUnit XML; results posted as a PR check
3. **Build** (matrix: `macos-14`, `macos-15-intel`, `windows-latest`, needs test):
   - PyInstaller build
   - **Smoke test**: launches the built binary and verifies it stays alive for 10 seconds

### `bump.yml` — runs on push to `Main`

- Serialised with a `concurrency` group (`cancel-in-progress: false`) to prevent races when multiple PRs merge in quick succession.
- Commitizen inspects commits since the last tag.
- If releasable commits exist: bumps `pyproject.toml`, commits the change, pushes a `vX.Y.Z` annotated tag, then dispatches `release.yml` via `workflow_dispatch`.
- If the latest tag has no published GitHub Release (e.g. a previous release run failed): re-dispatches `release.yml` without bumping.
- If nothing to do: exits cleanly (no-op).
- Uses `GITHUB_TOKEN` only — **no PAT required**. The `actions: write` permission allows dispatching `release.yml`.

### `release.yml` — triggered by `workflow_dispatch` (from `bump.yml` or manually)

1. **Build** (same matrix as CI) — build + smoke test per platform
2. **Publish** — creates a GitHub Release with the zip artifacts and auto-generated release notes

`workflow_dispatch` requires a `tag` input (e.g. `v1.2.3`) and checks out at that tag. This is also the mechanism used by `bump.yml` to trigger a release after a version bump.

---

## PyInstaller build notes

- The spec file `MultiChannelWavMixer.spec` is the single source of truth for the build.
- `numba` and `llvmlite` are listed in `excludes` — they must not be bundled.
- Hidden imports and data files are declared explicitly in the spec; update them when adding new dependencies that PyInstaller cannot auto-detect.
- On macOS the output is `dist/MultiChannelWavMixer.app`; on Windows it is `dist/MultiChannelWavMixer/` (a folder, no single-file exe).

---

## README maintenance

**After every significant change, review `README.md` and update it if needed.**

Changes that typically require README updates:
- New or removed features visible to the end user
- Changes to the GUI layout or controls
- New or changed CLI / run commands
- Dependency or Python version changes
- Changes to the CI/CD pipeline description
- Changes to the project structure (files added/removed/renamed)
- Changes to the `mixer_utils.py` public API table
- Version bump strategy or commit convention changes

The README is the primary user-facing and contributor-facing documentation. Keep it accurate.
