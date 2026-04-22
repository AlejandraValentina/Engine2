# AGENTS.md

## Role Of `gui/`
- The GUI is an orchestration and visualization layer over existing backend behavior.
- Prefer calling reusable backend modules and report builders instead of recreating logic in widgets.

## Non-Negotiable GUI Rules
- Do not reimplement compare, staged calibration, diagnostics, validation, A/B comparison, sensitivity, or optimization logic inside the GUI.
- Prefer backend helpers from `pywavedyn/*` and `core/*`; the GUI should trigger them, render results, and export artifacts.
- Do not suggest stronger certainty visually than the backend actually supports. Show missing signals, omitted stages, tradeoffs, and no-conclusion outcomes clearly.

## UX Expectations
- Use clear, actionable labels and error messages.
- Warnings should help the user proceed safely; soft warnings should not masquerade as fatal errors.
- When v1/v2 semantics differ, surface that difference visibly near the workflow where users compare or interpret results.
- Preserve offscreen/headless testability and existing GUI flows unless the task explicitly changes them.

## Editing Guidance
- Favor small, localized GUI changes over broad rewrites.
- If a needed capability is missing in the backend, add it there first instead of inventing a GUI-side workaround.
