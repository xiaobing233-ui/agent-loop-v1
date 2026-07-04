#!/usr/bin/env python3
"""Create one placeholder analysis JSON for a single task013 cover."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = REPO_ROOT / "outputs" / "task_013"
MANIFEST_FILE = TASK_DIR / "image_manifest.json"
PER_COVER_DIR = TASK_DIR / "per_cover"


def load_manifest() -> list[dict]:
    if not MANIFEST_FILE.exists():
        raise FileNotFoundError(f"Missing manifest: {MANIFEST_FILE}")

    data = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("image_manifest.json must be a JSON array")
    return data


def find_cover(manifest: list[dict], cover_id: str) -> dict:
    matches = [item for item in manifest if item.get("cover_id") == cover_id]
    if not matches:
        raise ValueError(f"cover_id not found: {cover_id}")
    if len(matches) > 1:
        raise ValueError(f"cover_id is duplicated: {cover_id}")
    return matches[0]


def build_placeholder(record: dict) -> dict:
    return {
        "cover_id": record.get("cover_id", ""),
        "source_file": record.get("source_file", ""),
        "file_name": record.get("file_name", ""),
        "label": record.get("label", "unknown"),
        "analysis_status": "needs_model_analysis",
        "scene_classification": "Education",
        "frame_type": "mixed",
        "face_signal": 0.0,
        "emotion_signal": 0.0,
        "composition_signal": 0.0,
        "information_density": 0.0,
        "event_signal": 0.0,
        "title_hook_type": [],
        "layout_type": "split_narrative",
        "click_logic": "",
        "performance_label": "low",
        "reusable_pattern": "",
        "scoring_notes": "Placeholder only; visual model analysis was not run.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate one task013 per-cover placeholder analysis JSON."
    )
    parser.add_argument("--cover-id", required=True, help="Example: cover_001")
    args = parser.parse_args()

    try:
        manifest = load_manifest()
        record = find_cover(manifest, args.cover_id)
        output = build_placeholder(record)

        PER_COVER_DIR.mkdir(parents=True, exist_ok=True)
        out_file = PER_COVER_DIR / f"{args.cover_id}.json"
        out_file.write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {out_file.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
