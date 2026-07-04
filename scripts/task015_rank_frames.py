#!/usr/bin/env python3
"""Rank successful task_015 frame scores."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = REPO_ROOT / "outputs" / "task_015"
FRAME_SCORE_DIR = TASK_DIR / "frame_scores"
RANKED_JSON = TASK_DIR / "ranked_frames.json"
TOP_MD = TASK_DIR / "top_candidates.md"


def load_scores() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(FRAME_SCORE_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("status") == "success":
            records.append(data)
    records.sort(key=lambda item: float(item.get("final_score", 0)), reverse=True)
    return records


def build_top_markdown(records: list[dict[str, Any]], top_n: int) -> str:
    lines = [
        "# Task 015 Top Frame Candidates",
        "",
        f"- Successful scored frames: {len(records)}",
        f"- Top N requested: {top_n}",
        "",
    ]
    if not records:
        lines.append("No successful frame scores found.")
        return "\n".join(lines) + "\n"

    for rank, record in enumerate(records[:top_n], start=1):
        risks = record.get("visual_risk_notes") or []
        signals = record.get("generation_prompt_signals") or []
        lines.extend(
            [
                f"## {rank}. {record.get('frame_id', '')}",
                "",
                f"- timestamp_sec: {record.get('timestamp_sec', '')}",
                f"- final_score: {record.get('final_score', '')}",
                f"- decision_band: {record.get('decision_band', '')}",
                f"- 推荐原因: {record.get('recommendation', '')}",
                f"- 风险提示: {'; '.join(map(str, risks)) if risks else 'None'}",
                f"- 后续生成封面 prompt 可用信号: {'; '.join(map(str, signals)) if signals else 'None'}",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank successful task_015 frame scores.")
    parser.add_argument("--top-n", type=int, default=10)
    args = parser.parse_args()

    try:
        if args.top_n <= 0:
            raise ValueError("--top-n must be greater than 0")
        records = load_scores()
        TASK_DIR.mkdir(parents=True, exist_ok=True)
        RANKED_JSON.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        TOP_MD.write_text(build_top_markdown(records, args.top_n), encoding="utf-8")
    except Exception as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1

    print(f"ranked {len(records)} successful frames")
    print(f"wrote {RANKED_JSON.relative_to(REPO_ROOT)}")
    print(f"wrote {TOP_MD.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
