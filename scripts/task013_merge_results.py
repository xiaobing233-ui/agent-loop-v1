#!/usr/bin/env python3
"""Merge task013 per-cover JSON files into aggregate outputs."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = REPO_ROOT / "outputs" / "task_013"
MANIFEST_FILE = TASK_DIR / "image_manifest.json"
PER_COVER_DIR = TASK_DIR / "per_cover"
EXPECTED_COUNT_FALLBACK = 19

DATASET_FILE = TASK_DIR / "dataset.json"
PATTERN_SUMMARY_FILE = TASK_DIR / "pattern_summary.md"
RESULT_JSON_FILE = TASK_DIR / "result.json"
RESULT_MD_FILE = TASK_DIR / "result.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest() -> list[dict]:
    if not MANIFEST_FILE.exists():
        return []
    data = read_json(MANIFEST_FILE)
    if not isinstance(data, list):
        raise ValueError("image_manifest.json must be a JSON array")
    return data


def load_per_cover_records() -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    errors: list[str] = []
    for path in sorted(PER_COVER_DIR.glob("*.json")):
        try:
            data = read_json(path)
            if not isinstance(data, dict):
                raise ValueError("per-cover file must contain a JSON object")
            records.append(data)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    records.sort(key=lambda item: item.get("cover_id", ""))
    return records, errors


def counter(records: list[dict], key: str) -> dict[str, int]:
    counts = Counter(str(item.get(key, "")) for item in records)
    return dict(sorted(counts.items()))


def nonempty_counter(records: list[dict], key: str) -> dict[str, int]:
    counts = Counter(str(item.get(key, "")) for item in records if item.get(key))
    return dict(sorted(counts.items()))


def list_missing_cover_ids(manifest: list[dict], records: list[dict]) -> list[str]:
    present = {item.get("cover_id") for item in records}
    return [
        str(item.get("cover_id"))
        for item in manifest
        if item.get("cover_id") and item.get("cover_id") not in present
    ]


def determine_status(records: list[dict], expected_count: int, errors: list[str]) -> str:
    if errors or len(records) < expected_count:
        return "failed"
    if any(item.get("analysis_status") != "success" for item in records):
        return "partial"
    return "success"


def build_pattern_summary(records: list[dict], expected_count: int) -> str:
    status_counts = counter(records, "analysis_status")
    label_counts = counter(records, "label")
    scene_counts = nonempty_counter(records, "scene_classification")
    frame_counts = nonempty_counter(records, "frame_type")
    layout_counts = nonempty_counter(records, "layout_type")
    performance_counts = nonempty_counter(records, "performance_label")
    reusable_patterns = nonempty_counter(records, "reusable_pattern")

    def lines_from_counts(title: str, counts: dict[str, int]) -> list[str]:
        lines = [f"## {title}"]
        if not counts:
            lines.append("- No data")
        else:
            lines.extend(f"- {name}: {value}" for name, value in counts.items())
        return lines

    lines = [
        "# Task 013 Pattern Summary",
        "",
        f"- Records merged: {len(records)} / {expected_count}",
        "- Source: per-cover JSON files only",
        "- Model calls: none",
        "",
    ]
    for title, counts in [
        ("Analysis Status", status_counts),
        ("Labels", label_counts),
        ("Scene Classification", scene_counts),
        ("Frame Type", frame_counts),
        ("Layout Type", layout_counts),
        ("Performance Label", performance_counts),
        ("Reusable Pattern", reusable_patterns),
    ]:
        lines.extend(lines_from_counts(title, counts))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_result_markdown(result: dict) -> str:
    lines = [
        "# Task 013 Result",
        "",
        f"- Status: {result['status']}",
        f"- Expected covers: {result['expected_count']}",
        f"- Per-cover files found: {result['per_cover_count']}",
        f"- Dataset records: {result['dataset_count']}",
        f"- All analyses successful: {str(result['all_success']).lower()}",
        f"- Missing covers: {len(result['missing_cover_ids'])}",
        f"- Invalid files: {len(result['errors'])}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        manifest = load_manifest()
        expected_count = len(manifest) or EXPECTED_COUNT_FALLBACK
        records, errors = load_per_cover_records()
        missing_cover_ids = list_missing_cover_ids(manifest, records)
        status = determine_status(records, expected_count, errors)

        result = {
            "status": status,
            "expected_count": expected_count,
            "per_cover_count": len(records),
            "dataset_count": len(records),
            "all_success": bool(records)
            and len(records) == expected_count
            and all(item.get("analysis_status") == "success" for item in records),
            "analysis_status_counts": counter(records, "analysis_status"),
            "label_counts": counter(records, "label"),
            "scene_classification_counts": nonempty_counter(records, "scene_classification"),
            "frame_type_counts": nonempty_counter(records, "frame_type"),
            "layout_type_counts": nonempty_counter(records, "layout_type"),
            "performance_label_counts": nonempty_counter(records, "performance_label"),
            "missing_cover_ids": missing_cover_ids,
            "errors": errors,
        }

        TASK_DIR.mkdir(parents=True, exist_ok=True)
        DATASET_FILE.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        PATTERN_SUMMARY_FILE.write_text(
            build_pattern_summary(records, expected_count),
            encoding="utf-8",
        )
        RESULT_JSON_FILE.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        RESULT_MD_FILE.write_text(build_result_markdown(result), encoding="utf-8")
    except Exception as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1

    print(f"merged {len(records)} records; status {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
