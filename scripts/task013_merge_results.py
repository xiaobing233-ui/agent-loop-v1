#!/usr/bin/env python3
"""Merge task013 per-cover V2 JSON files into dataset and summaries."""

from __future__ import annotations

import json
import statistics
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


def load_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_FILE.exists():
        return []
    data = read_json(MANIFEST_FILE)
    if not isinstance(data, list):
        raise ValueError("image_manifest.json must be a JSON array")
    return data


def load_per_cover_records() -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in sorted(PER_COVER_DIR.glob("cover_*.json")):
        try:
            data = read_json(path)
            if not isinstance(data, dict):
                raise ValueError("per-cover file must contain a JSON object")
            records.append(data)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    records.sort(key=lambda item: str(item.get("cover_id", "")))
    return records, errors


def nested(record: dict[str, Any], *keys: str, default: Any = "") -> Any:
    value: Any = record
    for key in keys:
        if not isinstance(value, dict):
            return default
        value = value.get(key, default)
    return value


def count_values(records: list[dict[str, Any]], key_path: tuple[str, ...]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        value = nested(record, *key_path)
        if isinstance(value, list):
            counts.update(str(item) for item in value if item)
        elif value:
            counts[str(value)] += 1
    return dict(counts.most_common())


def avg(records: list[dict[str, Any]], key_path: tuple[str, ...]) -> float | None:
    values: list[float] = []
    for record in records:
        value = nested(record, *key_path, default=None)
        if isinstance(value, (int, float)):
            values.append(float(value))
    if not values:
        return None
    return round(statistics.fmean(values), 3)


def list_missing_cover_ids(
    manifest: list[dict[str, Any]], records: list[dict[str, Any]]
) -> list[str]:
    present = {record.get("cover_id") for record in records}
    return [
        str(item.get("cover_id"))
        for item in manifest
        if item.get("cover_id") and item.get("cover_id") not in present
    ]


def is_success(record: dict[str, Any]) -> bool:
    return record.get("status") == "success" and record.get("analysis_status") == "success"


def determine_status(
    records: list[dict[str, Any]], expected_count: int, errors: list[str]
) -> str:
    if errors or len(records) < expected_count:
        return "failed"
    if any(not is_success(record) for record in records):
        return "partial"
    return "success"


def summarize_group(title: str, records: list[dict[str, Any]]) -> list[str]:
    success_records = [record for record in records if is_success(record)]
    lines = [f"## {title}", f"- 样本数: {len(records)}，成功分析: {len(success_records)}"]
    if not success_records:
        lines.append("- 暂无可汇总的成功视觉分析记录。")
        return lines

    for label, key_path in [
        ("主要场景", ("decision_factors", "scene_classification")),
        ("画面帧型", ("decision_factors", "frame_type")),
        ("图文布局", ("decision_factors", "layout_type")),
        ("标题钩子", ("decision_factors", "title_hook_type")),
    ]:
        counts = count_values(success_records, key_path)
        top = ", ".join(f"{name}({count})" for name, count in list(counts.items())[:5])
        lines.append(f"- {label}: {top or '暂无'}")

    patterns = [
        nested(record, "decision_factors", "reusable_pattern")
        for record in success_records
        if nested(record, "decision_factors", "reusable_pattern")
    ]
    if patterns:
        lines.append("- 可复用模式:")
        lines.extend(f"  - {pattern}" for pattern in patterns[:6])
    return lines


def generation_advice(records: list[dict[str, Any]]) -> list[str]:
    success_records = [record for record in records if is_success(record)]
    lines = ["## 对 GPT image2 prompt 的生成建议"]
    if not success_records:
        lines.append("- 暂无成功视觉分析记录，不能生成可靠建议。")
        return lines

    for label, key_path in [
        ("图生图方向", ("generation_strategy", "image2_prompt_direction")),
        ("主体保留", ("generation_strategy", "subject_preservation")),
        ("背景策略", ("generation_strategy", "background_strategy")),
        ("标题区域", ("generation_strategy", "title_area_planning")),
    ]:
        values = [
            nested(record, *key_path)
            for record in success_records
            if nested(record, *key_path)
        ]
        lines.append(f"- {label}: {' / '.join(values[:5]) if values else '暂无'}")

    constraints = count_values(success_records, ("generation_strategy", "negative_constraints"))
    if constraints:
        top = ", ".join(f"{name}({count})" for name, count in list(constraints.items())[:8])
        lines.append(f"- 负向约束高频项: {top}")
    return lines


def scoring_advice(records: list[dict[str, Any]]) -> list[str]:
    success_records = [record for record in records if is_success(record)]
    satisfied = [record for record in success_records if record.get("label") == "satisfied"]
    unsatisfied = [record for record in success_records if record.get("label") == "unsatisfied"]
    metrics = [
        ("face_signal", ("decision_factors", "face_signal")),
        ("emotion_signal", ("decision_factors", "emotion_signal")),
        ("composition_signal", ("decision_factors", "composition_signal")),
        ("information_density", ("decision_factors", "information_density")),
        ("event_signal", ("decision_factors", "event_signal")),
    ]
    lines = ["## 后续 Frame Scoring 权重校准建议"]
    if not satisfied or not unsatisfied:
        lines.append("- 满意/不满意成功样本不足，暂不做权重差异判断。")
        return lines

    deltas: list[tuple[str, float, float, float]] = []
    for name, key_path in metrics:
        sat_avg = avg(satisfied, key_path)
        unsat_avg = avg(unsatisfied, key_path)
        if sat_avg is None or unsat_avg is None:
            continue
        deltas.append((name, sat_avg, unsat_avg, round(sat_avg - unsat_avg, 3)))
    for name, sat_avg, unsat_avg, delta in sorted(deltas, key=lambda item: abs(item[3]), reverse=True):
        direction = "提高权重" if delta > 0 else "降低或重检权重"
        lines.append(
            f"- {name}: 满意均值 {sat_avg}，不满意均值 {unsat_avg}，差值 {delta}，建议{direction}。"
        )
    return lines


def decision_rules(records: list[dict[str, Any]]) -> list[str]:
    success_records = [record for record in records if is_success(record)]
    lines = ["## 可复用封面决策规则"]
    if not success_records:
        lines.append("- 暂无成功视觉分析记录，不能沉淀决策规则。")
        return lines

    satisfied = [record for record in success_records if record.get("label") == "satisfied"]
    source = satisfied or success_records
    for label, key_path in [
        ("优先场景", ("decision_factors", "scene_classification")),
        ("优先帧型", ("decision_factors", "frame_type")),
        ("优先布局", ("decision_factors", "layout_type")),
        ("优先标题钩子", ("decision_factors", "title_hook_type")),
    ]:
        counts = count_values(source, key_path)
        top = next(iter(counts), "")
        if top:
            lines.append(f"- {label}: {top}")
    lines.append("- 对低分或不满意样本，优先检查标题可读性、主体清晰度、构图重心和生成瑕疵风险。")
    return lines


def build_pattern_summary(records: list[dict[str, Any]], expected_count: int) -> str:
    satisfied = [record for record in records if record.get("label") == "satisfied"]
    unsatisfied = [record for record in records if record.get("label") == "unsatisfied"]
    lines = [
        "# Task 013 Cover Reverse Pattern Summary",
        "",
        f"- Records merged: {len(records)} / {expected_count}",
        f"- Success: {sum(1 for record in records if is_success(record))}",
        f"- Failed: {sum(1 for record in records if not is_success(record))}",
        "- Source: local per_cover JSON only; merge step made no model calls.",
        "",
    ]
    for section in [
        summarize_group("满意封面的共性", satisfied),
        summarize_group("不满意封面的共性", unsatisfied),
        decision_rules(records),
        generation_advice(records),
        scoring_advice(records),
    ]:
        lines.extend(section)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_result_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Task 013 Result",
        "",
        f"- Status: {result['status']}",
        f"- Expected covers: {result['expected_count']}",
        f"- Per-cover files found: {result['per_cover_count']}",
        f"- Dataset records: {result['dataset_count']}",
        f"- Success: {result['success_count']}",
        f"- Failed: {result['failed_count']}",
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
        success_count = sum(1 for record in records if is_success(record))
        failed_count = len(records) - success_count
        result = {
            "status": status,
            "expected_count": expected_count,
            "per_cover_count": len(records),
            "dataset_count": len(records),
            "success_count": success_count,
            "failed_count": failed_count,
            "label_counts": count_values(records, ("label",)),
            "analysis_status_counts": count_values(records, ("analysis_status",)),
            "scene_classification_counts": count_values(
                records, ("decision_factors", "scene_classification")
            ),
            "frame_type_counts": count_values(records, ("decision_factors", "frame_type")),
            "layout_type_counts": count_values(records, ("decision_factors", "layout_type")),
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
