#!/usr/bin/env python3
"""Extract candidate frames from one video for task_015."""

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
FRAMES_DIR = TASK_DIR / "frames"
MANIFEST_FILE = TASK_DIR / "frame_manifest.json"
EXTRACTION_VERSION = "task015_frame_extraction_v0.1"


def find_binary(name: str) -> str | None:
    return shutil.which(name)


def ffmpeg_from_imageio() -> str | None:
    try:
        import imageio_ffmpeg
    except Exception:
        return None
    try:
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    return ffmpeg if ffmpeg and Path(ffmpeg).exists() else None


def require_ffmpeg() -> str:
    ffmpeg = os.environ.get("TASK015_FFMPEG_BIN")
    if ffmpeg:
        return ffmpeg

    ffmpeg = find_binary("ffmpeg")
    if ffmpeg:
        return ffmpeg

    ffmpeg = ffmpeg_from_imageio()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found; install ffmpeg or pip install imageio-ffmpeg")
    return ffmpeg


def ffmpeg_version_line(ffmpeg_bin: str) -> str:
    result = subprocess.run(
        [ffmpeg_bin, "-version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg -version failed")
    return result.stdout.splitlines()[0] if result.stdout.splitlines() else ""


def read_frame_dimensions_with_pillow(frame_path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(frame_path) as image:
            width, height = image.size
        return (int(width), int(height))
    except Exception:
        return None


def read_frame_dimensions_with_sips(frame_path: Path) -> tuple[int, int] | None:
    sips = find_binary("sips") or "/usr/bin/sips"
    if not Path(sips).exists():
        return None
    result = subprocess.run(
        [sips, "-g", "pixelWidth", "-g", "pixelHeight", str(frame_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return None
    width_match = re.search(r"pixelWidth:\s*(\d+)", result.stdout)
    height_match = re.search(r"pixelHeight:\s*(\d+)", result.stdout)
    if not width_match or not height_match:
        return None
    return (int(width_match.group(1)), int(height_match.group(1)))


def read_frame_dimensions_with_ffprobe(frame_path: Path) -> tuple[int, int] | None:
    ffprobe = find_binary("ffprobe")
    if not ffprobe:
        return None
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
        str(frame_path),
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
        stream = payload.get("streams", [{}])[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
    except Exception:
        return None
    return (width, height) if width > 0 and height > 0 else None


def read_frame_dimensions_with_ffmpeg(frame_path: Path, ffmpeg_bin: str) -> tuple[int, int] | None:
    result = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-i", str(frame_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    text = "\n".join([result.stdout, result.stderr])
    matches = re.findall(r"(?<![.\w])(\d{2,5})x(\d{2,5})(?![.\w])", text)
    if not matches:
        return None
    width, height = matches[-1]
    return (int(width), int(height))


def read_frame_dimensions(frame_path: Path, ffmpeg_bin: str) -> tuple[int, int, str | None]:
    for reader in (
        read_frame_dimensions_with_pillow,
        read_frame_dimensions_with_sips,
        read_frame_dimensions_with_ffprobe,
    ):
        dimensions = reader(frame_path)
        if dimensions:
            return (dimensions[0], dimensions[1], None)

    dimensions = read_frame_dimensions_with_ffmpeg(frame_path, ffmpeg_bin)
    if dimensions:
        return (dimensions[0], dimensions[1], None)
    return (0, 0, "unable_to_read_frame_dimensions")


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


def extract_frames(
    video_path: Path, interval_sec: float, max_frames: int | None, ffmpeg_bin: str
) -> list[Path]:
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    output_pattern = FRAMES_DIR / "frame_%04d.jpg"
    command = [
        ffmpeg_bin,
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


def build_manifest(video_path: Path, frame_paths: list[Path], interval_sec: float, ffmpeg_bin: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, frame_path in enumerate(frame_paths, start=1):
        width, height, warning = read_frame_dimensions(frame_path, ffmpeg_bin)
        record = {
            "frame_id": f"frame_{index:04d}",
            "video_path": str(video_path),
            "frame_path": str(frame_path),
            "timestamp_sec": round((index - 1) * interval_sec, 3),
            "width": width,
            "height": height,
            "extraction_version": EXTRACTION_VERSION,
        }
        if warning:
            record["warning"] = warning
        records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract fixed-interval frames for task_015.")
    parser.add_argument("--video", help="Path to the input video file.")
    parser.add_argument("--interval-sec", type=float, default=2.0)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument(
        "--check-ffmpeg",
        action="store_true",
        help="Print the resolved ffmpeg path and version, then exit.",
    )
    args = parser.parse_args()

    try:
        if args.check_ffmpeg:
            ffmpeg = require_ffmpeg()
            print(f"ffmpeg_path: {ffmpeg}")
            print(f"ffmpeg_version: {ffmpeg_version_line(ffmpeg)}")
            return 0

        if not args.video:
            raise ValueError("--video is required unless --check-ffmpeg is used")
        video_path = Path(args.video).expanduser().resolve()
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")
        if args.interval_sec <= 0:
            raise ValueError("--interval-sec must be greater than 0")
        if args.max_frames is not None and args.max_frames <= 0:
            raise ValueError("--max-frames must be greater than 0")

        ffmpeg = require_ffmpeg()
        frame_paths = extract_frames(video_path, args.interval_sec, args.max_frames, ffmpeg)
        manifest = build_manifest(video_path, frame_paths, args.interval_sec, ffmpeg)
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
