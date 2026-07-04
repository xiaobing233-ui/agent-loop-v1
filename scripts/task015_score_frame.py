#!/usr/bin/env python3
"""Score exactly one extracted frame for task_015."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = REPO_ROOT / "outputs" / "task_015"
MANIFEST_FILE = TASK_DIR / "frame_manifest.json"
WEIGHTS_FILE = REPO_ROOT / "outputs" / "task_014" / "frame_scoring_weights.json"
PROMPT_FILE = REPO_ROOT / "prompts" / "task015_single_frame_scoring_prompt.md"
RUNTIME_PROMPT_DIR = TASK_DIR / "runtime_prompts"
CODEX_RAW_DIR = TASK_DIR / "codex_raw"
FRAME_SCORE_DIR = TASK_DIR / "frame_scores"
ANALYSIS_VERSION = "task015_frame_scoring_v0.1"
DEFAULT_BACKEND = "codex_cli"


class ScoringError(RuntimeError):
    """Raised when one-frame scoring cannot be completed."""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_FILE.exists():
        raise FileNotFoundError(f"Missing frame manifest: {MANIFEST_FILE}")
    data = load_json(MANIFEST_FILE)
    if not isinstance(data, list):
        raise ValueError("frame_manifest.json must be a JSON array")
    return data


def load_weights() -> dict[str, Any]:
    data = load_json(WEIGHTS_FILE)
    if not isinstance(data, dict):
        raise ValueError("frame_scoring_weights.json must be a JSON object")
    return data


def resolve_frame(
    manifest: list[dict[str, Any]], frame_id: str | None, index: int | None
) -> dict[str, Any]:
    if frame_id:
        matches = [item for item in manifest if item.get("frame_id") == frame_id]
        if not matches:
            raise ValueError(f"frame_id not found: {frame_id}")
        if len(matches) > 1:
            raise ValueError(f"frame_id duplicated: {frame_id}")
        return matches[0]
    if index is None:
        raise ValueError("Provide --frame-id or --index")
    if index < 1 or index > len(manifest):
        raise ValueError(f"--index must be between 1 and {len(manifest)}")
    return manifest[index - 1]


def find_codex_bin() -> str:
    configured = os.environ.get("TASK015_CODEX_BIN")
    if configured:
        return configured
    found = shutil.which("codex")
    if found:
        return found
    fallback = "/Applications/Codex.app/Contents/Resources/codex"
    if Path(fallback).exists():
        return fallback
    raise ScoringError("Codex CLI not found")


def sanitize_error(message: str) -> str:
    safe = str(message)
    for key in ("TASK015_CODEX_BIN",):
        value = os.environ.get(key)
        if value:
            safe = safe.replace(value, "[redacted]")
    return " ".join(safe.split())[:600]


def stderr_first_line(stderr: str) -> str:
    for line in stderr.splitlines():
        stripped = line.strip()
        if stripped:
            return sanitize_error(stripped)[:240]
    return ""


def parse_json_object_from_text(raw_text: str) -> dict[str, Any]:
    stripped = raw_text.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.S)
    if block_match:
        try:
            parsed = json.loads(block_match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(raw_text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw_text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ScoringError("raw output was not a JSON object")


def score_to_band(score: float, thresholds: dict[str, Any]) -> str:
    if score < float(thresholds.get("reject_below", 55)):
        return "reject"
    for band in ("weak_candidate", "acceptable_candidate", "strong_candidate", "top_candidate"):
        spec = thresholds.get(band, {})
        if float(spec.get("min", -1)) <= score <= float(spec.get("max", 101)):
            return band
    return "top_candidate" if score >= 85 else "unknown"


def normalize_dimension_scores(payload: dict[str, Any], weights: dict[str, Any]) -> list[dict[str, Any]]:
    raw_scores = payload.get("dimension_scores", [])
    if isinstance(raw_scores, dict):
        raw_scores = [
            {"dimension_id": key, "score": value} for key, value in raw_scores.items()
        ]
    if not isinstance(raw_scores, list):
        raw_scores = []

    by_id: dict[str, dict[str, Any]] = {}
    for item in raw_scores:
        if isinstance(item, dict) and item.get("dimension_id"):
            by_id[str(item["dimension_id"])] = item

    normalized: list[dict[str, Any]] = []
    for dimension in weights.get("dimensions", []):
        dimension_id = str(dimension.get("dimension_id"))
        source = by_id.get(dimension_id, {})
        score = float(source.get("score", source.get("raw_score", 0)) or 0)
        score = max(0.0, min(5.0, score))
        weight = float(dimension.get("weight", 0))
        normalized.append(
            {
                "dimension_id": dimension_id,
                "dimension_name": dimension.get("dimension_name", ""),
                "score": score,
                "weight": weight,
                "weighted_score": round(weight * score / 5.0, 3),
                "rationale": str(source.get("rationale", "")),
            }
        )
    return normalized


def normalize_penalties(payload: dict[str, Any], weights: dict[str, Any]) -> list[dict[str, Any]]:
    raw_penalties = payload.get("penalties", [])
    if not isinstance(raw_penalties, list):
        return []
    known = {item.get("penalty_id"): item for item in weights.get("penalties", [])}
    normalized: list[dict[str, Any]] = []
    for item in raw_penalties:
        if not isinstance(item, dict):
            continue
        penalty_id = item.get("penalty_id")
        spec = known.get(penalty_id, {})
        points = item.get("points", spec.get("points", 0))
        try:
            points = float(points)
        except (TypeError, ValueError):
            points = 0.0
        if points > 0:
            points = -points
        normalized.append(
            {
                "penalty_id": penalty_id or "",
                "name": item.get("name", spec.get("name", "")),
                "points": points,
                "reason": item.get("reason", item.get("trigger", "")),
            }
        )
    return normalized


def failure_payload(frame: dict[str, Any], error: str) -> dict[str, Any]:
    return {
        "frame_id": frame.get("frame_id", ""),
        "frame_path": frame.get("frame_path", ""),
        "timestamp_sec": frame.get("timestamp_sec", 0),
        "status": "failed",
        "analysis_version": ANALYSIS_VERSION,
        "dimension_scores": [],
        "penalties": [],
        "weighted_score": 0.0,
        "penalty_score": 0.0,
        "final_score": 0.0,
        "decision_band": "failed",
        "recommendation": "",
        "title_space_assessment": "",
        "subject_assessment": "",
        "visual_risk_notes": [],
        "generation_prompt_signals": [],
        "error_summary": sanitize_error(error),
    }


def normalize_payload(frame: dict[str, Any], payload: dict[str, Any], weights: dict[str, Any]) -> dict[str, Any]:
    dimensions = normalize_dimension_scores(payload, weights)
    penalties = normalize_penalties(payload, weights)
    weighted_score = round(sum(item["weighted_score"] for item in dimensions), 3)
    penalty_score = round(sum(item["points"] for item in penalties), 3)
    final_score = round(max(0.0, min(100.0, weighted_score + penalty_score)), 3)
    return {
        "frame_id": frame.get("frame_id", ""),
        "frame_path": frame.get("frame_path", ""),
        "timestamp_sec": frame.get("timestamp_sec", 0),
        "status": "success",
        "analysis_version": ANALYSIS_VERSION,
        "dimension_scores": dimensions,
        "penalties": penalties,
        "weighted_score": weighted_score,
        "penalty_score": penalty_score,
        "final_score": final_score,
        "decision_band": score_to_band(final_score, weights.get("decision_thresholds", {})),
        "recommendation": str(payload.get("recommendation", "")),
        "title_space_assessment": str(payload.get("title_space_assessment", "")),
        "subject_assessment": str(payload.get("subject_assessment", "")),
        "visual_risk_notes": payload.get("visual_risk_notes", [])
        if isinstance(payload.get("visual_risk_notes"), list)
        else [],
        "generation_prompt_signals": payload.get("generation_prompt_signals", [])
        if isinstance(payload.get("generation_prompt_signals"), list)
        else [],
        "error_summary": "",
    }


def build_prompt(frame: dict[str, Any], weights: dict[str, Any]) -> str:
    template = PROMPT_FILE.read_text(encoding="utf-8")
    metadata = {
        "frame_id": frame.get("frame_id"),
        "frame_path": frame.get("frame_path"),
        "timestamp_sec": frame.get("timestamp_sec"),
        "analysis_version": ANALYSIS_VERSION,
    }
    return (
        template.strip()
        + "\n\nFrame metadata:\n"
        + json.dumps(metadata, ensure_ascii=False, indent=2)
        + "\n\nFrame scoring weights:\n"
        + json.dumps(weights, ensure_ascii=False, indent=2)
        + "\n"
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_codex_cli(frame: dict[str, Any], weights: dict[str, Any], timeout: int, dry_run: bool) -> dict[str, Any] | None:
    prompt_text = build_prompt(frame, weights)
    RUNTIME_PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    prompt_path = RUNTIME_PROMPT_DIR / f"{frame['frame_id']}.md"
    prompt_path.write_text(prompt_text, encoding="utf-8")
    if dry_run:
        return None

    CODEX_RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = CODEX_RAW_DIR / f"{frame['frame_id']}.txt"
    command = [
        find_codex_bin(),
        "-a",
        "never",
        "exec",
        "--skip-git-repo-check",
        "-C",
        str(REPO_ROOT),
        "-o",
        rel(raw_path),
        "-",
    ]
    result = subprocess.run(
        command,
        input=prompt_text,
        cwd=str(REPO_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if result.returncode != 0:
        message = f"Codex CLI failed exit_code={result.returncode}"
        stderr_line = stderr_first_line(result.stderr)
        if stderr_line:
            message += f"; stderr_first_line={stderr_line}"
        raise ScoringError(message)
    if not raw_path.exists():
        raise ScoringError("Codex CLI completed but did not write raw output")
    raw_payload = parse_json_object_from_text(raw_path.read_text(encoding="utf-8", errors="replace"))
    return normalize_payload(frame, raw_payload, weights)


def main() -> int:
    parser = argparse.ArgumentParser(description="Score one task_015 frame.")
    parser.add_argument("--frame-id", help="Example: frame_0001")
    parser.add_argument("--index", type=int, help="1-based frame manifest index.")
    parser.add_argument("--backend", choices=["codex_cli"], default=DEFAULT_BACKEND)
    parser.add_argument("--dry-run", action="store_true", help="Only write runtime prompt; do not call Codex CLI.")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    try:
        manifest = load_manifest()
        weights = load_weights()
        frame = resolve_frame(manifest, args.frame_id, args.index)
        payload = run_codex_cli(frame, weights, args.timeout, args.dry_run)
        if payload is None:
            print(f"dry-run wrote {rel(RUNTIME_PROMPT_DIR / (frame['frame_id'] + '.md'))}")
            return 0
    except Exception as exc:
        if "frame" in locals():
            payload = failure_payload(frame, str(exc))
        else:
            print(f"failed: {sanitize_error(str(exc))}", file=sys.stderr)
            return 1

    output_path = FRAME_SCORE_DIR / f"{payload['frame_id']}.json"
    write_json(output_path, payload)
    print(f"wrote {rel(output_path)} status={payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
