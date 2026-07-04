#!/usr/bin/env python3
"""Extract candidate frames from one video for task_015."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = REPO_ROOT / "outputs" / "task_015"
FRAMES_DIR = TASK_DIR / "frames"
MANIFEST_FILE = TASK_DIR / "frame_manifest.json"
EXTRACTION_VERSION = "task015_frame_extraction_v0.1"


def find_binary(name: str) -> str | None:
    return shutil.which(name)


def require_ffmpeg() -> str:
    ffmpeg = find_binary("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found. Install ffmpeg or add it to PATH.")
    return ffmpeg


def probe_video_dimensions(video_path: Path) -> tuple[int, int]:
    ffprobe = find_binary("ffprobe")
    if not ffprobe:
        return (0, 0)
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        return (0, 0)
    try:
        payload = json.loads(result.stdout)
        stream = payload.get("streams", [{}])[0]
        return (int(stream.get("width") or 0), int(stream.get("height") or 0))
    except Exception:
        return (0, 0)


def extract_frames(video_path: Path, interval_sec: float, max_frames: int | None) -> list[Path]:
    ffmpeg = require_ffmpeg()
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    output_pattern = FRAMES_DIR / "frame_%04d.jpg"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        f"fps=1/{interval_sec}",
        "-q:v",
        "3",
    ]
    if max_frames:
        command.extend(["-frames:v", str(max_frames)])
    command.append(str(output_pattern))

    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg frame extraction failed")
    return sorted(FRAMES_DIR.glob("frame_*.jpg"))


def build_manifest(
    video_path: Path, frame_paths: list[Path], interval_sec: float, width: int, height: int
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, frame_path in enumerate(frame_paths, start=1):
        records.append(
            {
                "frame_id": f"frame_{index:04d}",
                "video_path": str(video_path),
                "frame_path": str(frame_path),
                "timestamp_sec": round((index - 1) * interval_sec, 3),
                "width": width,
                "height": height,
                "extraction_version": EXTRACTION_VERSION,
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract fixed-interval frames for task_015.")
    parser.add_argument("--video", required=True, help="Path to the input video file.")
    parser.add_argument("--interval-sec", type=float, default=2.0)
    parser.add_argument("--max-frames", type=int, default=None)
    args = parser.parse_args()

    try:
        video_path = Path(args.video).expanduser().resolve()
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")
        if args.interval_sec <= 0:
            raise ValueError("--interval-sec must be greater than 0")
        if args.max_frames is not None and args.max_frames <= 0:
            raise ValueError("--max-frames must be greater than 0")

        frame_paths = extract_frames(video_path, args.interval_sec, args.max_frames)
        width, height = probe_video_dimensions(video_path)
        manifest = build_manifest(video_path, frame_paths, args.interval_sec, width, height)
        TASK_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST_FILE.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1

    print(f"extracted {len(frame_paths)} frames")
    print(f"wrote {MANIFEST_FILE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
