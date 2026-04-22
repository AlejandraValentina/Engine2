from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


BUNDLE_TYPE = "real_dyno_analysis_bundle"
BUNDLE_VERSION = 1


def _artifact_context(payload: dict) -> dict:
    context: dict[str, object] = {}
    if not isinstance(payload, dict):
        return context

    typed_context = payload.get("context")
    if isinstance(typed_context, dict) and typed_context:
        return {
            str(key): value
            for key, value in typed_context.items()
            if value not in {None, ""}
        }

    dataset = payload.get("dataset")
    if isinstance(dataset, dict):
        if dataset.get("dataset_id"):
            context["dataset_id"] = str(dataset["dataset_id"])
        if dataset.get("engine_id"):
            context["engine_id"] = str(dataset["engine_id"])
        if dataset.get("preset_path"):
            context["preset_path"] = str(dataset["preset_path"])
        return context

    cases = payload.get("cases")
    if isinstance(cases, list) and cases:
        first = cases[0]
        if isinstance(first, dict):
            case_dataset = first.get("dataset")
            if isinstance(case_dataset, dict):
                if case_dataset.get("dataset_id"):
                    context["dataset_id"] = str(case_dataset["dataset_id"])
                if case_dataset.get("engine_id"):
                    context["engine_id"] = str(case_dataset["engine_id"])
                if case_dataset.get("preset_path"):
                    context["preset_path"] = str(case_dataset["preset_path"])
    return context


def manifest_entry(*, artifact_type: str, filename: str, payload: object) -> dict:
    entry = {
        "artifact_type": str(artifact_type),
        "filename": str(filename),
    }
    if isinstance(payload, dict):
        context = _artifact_context(payload)
        if context:
            entry["context"] = context
    return entry


def build_manifest(entries: list[dict]) -> dict:
    return {
        "bundle_type": BUNDLE_TYPE,
        "bundle_version": BUNDLE_VERSION,
        "generated_at_utc": dt.datetime.utcnow().isoformat() + "Z",
        "artifact_count": len(entries),
        "artifacts": entries,
    }


def write_manifest(out_dir: Path, entries: list[dict]) -> Path:
    path = out_dir / "manifest.json"
    payload = build_manifest(entries)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
