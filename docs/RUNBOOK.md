# RUNBOOK

## Installation (base)
```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

## GUI extras (PySide6)
Install PySide6 if you want the GUI or GUI tests:
```bash
python -m pip install PySide6
```

Verify the GUI starts:
```bash
python main.py
```

## CLI sanity check
```bash
python -m pywavedyn.cli --help
```

## GUI smoke tests (offscreen)
Use offscreen rendering for headless CI:
```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_gui_import_smoke.py tests/test_gui_offscreen_window_smoke.py
```

## Troubleshooting Qt
- **Missing platform plugin**: set `QT_QPA_PLATFORM=offscreen` (headless) or `QT_QPA_PLATFORM=windows` (Windows desktop) before running.
- **Fonts/visual glitches**: confirm PySide6 is installed in the same Python environment as the CLI.
- **Linux headless**: ensure basic X11/wayland packages are present; use offscreen mode for tests.
