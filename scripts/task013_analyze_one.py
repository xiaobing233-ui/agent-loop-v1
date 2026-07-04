#!/usr/bin/env python3
"""Analyze exactly one task013 cover image.

Default backend: codex_cli.
Optional backend: direct_api, only when explicitly requested.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = REPO_ROOT / "outputs" / "task_013"
MANIFEST_FILE = TASK_DIR / "image_manifest.json"
PROMPT_FILE = REPO_ROOT / "prompts" / "task013_single_cover_prompt.md"
PER_COVER_DIR = TASK_DIR / "per_cover"
RUNTIME_IMAGE_DIR = TASK_DIR / "runtime_images"
RUNTIME_PROMPT_DIR = TASK_DIR / "runtime_prompts"
CODEX_RAW_DIR = TASK_DIR / "codex_raw"

ANALYSIS_VERSION = "cover_reverse_dataset_v2_file_only_2026-07-04"
DEFAULT_MODEL = "gpt-4o"
DEFAULT_BACKEND = "codex_cli"


class AnalysisError(RuntimeError):
    """Raised when one-cover analysis cannot be completed."""


def load_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_FILE.exists():
        raise FileNotFoundError(f"Missing manifest: {MANIFEST_FILE}")
    data = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("image_manifest.json must be a JSON array")
    return data


def resolve_record(
    manifest: list[dict[str, Any]], cover_id: str | None, index: int | None
) -> dict[str, Any]:
    if cover_id:
        matches = [item for item in manifest if item.get("cover_id") == cover_id]
        if not matches:
            raise ValueError(f"cover_id not found: {cover_id}")
        if len(matches) > 1:
            raise ValueError(f"cover_id is duplicated: {cover_id}")
        return matches[0]

    if index is None:
        raise ValueError("Provide --id/--cover-id or --index")
    if index < 1 or index > len(manifest):
        raise ValueError(f"--index must be between 1 and {len(manifest)}")
    return manifest[index - 1]


def source_path(record: dict[str, Any]) -> str:
    return str(record.get("source_file") or record.get("source_path") or "")


def cover_output_path(record: dict[str, Any]) -> Path:
    return PER_COVER_DIR / f"{record['cover_id']}.json"


def sanitize_error(message: str) -> str:
    safe = str(message)
    for key in (
        "TASK013_API_KEY",
        "OPENAI_API_KEY",
        "RBAPI_API_KEY",
        "TASK013_BASE_URL",
        "OPENAI_BASE_URL",
        "RBAPI_BASE_URL",
    ):
        value = os.environ.get(key)
        if value:
            safe = safe.replace(value, "[redacted]")
    return " ".join(safe.split())[:600]


def base_record(record: dict[str, Any]) -> dict[str, Any]:
    src = source_path(record)
    file_name = str(record.get("file_name") or Path(src).name)
    label = str(record.get("label") or "unknown")
    cover_id = str(record.get("cover_id") or "")
    return {
        "cover_id": cover_id,
        "source_path": src,
        "file_name": file_name,
        "label": label,
        "status": "failed",
        "analysis_status": "failed",
        "analysis_version": ANALYSIS_VERSION,
        "meta": {
            "cover_id": cover_id,
            "image_file": file_name,
            "video_type": "",
            "publish_channel": "视频号",
            "performance_label": label,
            "performance_metric": "",
            "business_goal": "Cover Decision + Generation System dataset calibration",
        },
        "image_level_observations": {
            "primary_subject": "",
            "visible_text_summary": "",
            "visual_hierarchy": "",
            "notable_design_elements": [],
        },
        "decision_factors": {
            "scene_classification": "",
            "frame_type": "",
            "face_signal": 0.0,
            "emotion_signal": 0.0,
            "composition_signal": 0.0,
            "information_density": 0.0,
            "event_signal": 0.0,
            "product_visibility": "",
            "title_hook_type": [],
            "layout_type": "",
            "click_logic": "",
            "reusable_pattern": "",
        },
        "generation_strategy": {
            "generation_mode": "",
            "reference_frame_usage": "",
            "subject_preservation": "",
            "background_strategy": "",
            "title_area_planning": "",
            "brand_element_strategy": "",
            "image2_prompt_direction": "",
            "negative_constraints": [],
            "generation_risk": "",
        },
        "qa_findings": {
            "face_quality_check": "",
            "product_accuracy_check": "",
            "text_area_check": "",
            "brand_consistency_check": "",
            "clickability_check": "",
            "platform_fit_check": "",
            "ai_artifact_risk": "",
            "final_usability": "failed",
            "revision_instruction": "",
        },
        "reusable_prompt_signals": [],
        "risk_notes": [],
        "error_summary": "",
    }


def merge_dict(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge_dict(base[key], value)
        elif key in base:
            base[key] = value
    return base


def normalize_analysis(record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    normalized = merge_dict(base_record(record), payload)
    normalized["cover_id"] = str(record.get("cover_id") or "")
    normalized["source_path"] = source_path(record)
    normalized["file_name"] = str(record.get("file_name") or Path(normalized["source_path"]).name)
    normalized["label"] = str(record.get("label") or "unknown")
    normalized["analysis_version"] = ANALYSIS_VERSION
    normalized["status"] = "success" if normalized.get("status") == "success" else normalized.get("status", "success")
    normalized["analysis_status"] = normalized.get("analysis_status") or normalized["status"]
    if normalized["status"] == "success":
        normalized["analysis_status"] = "success"
        normalized["error_summary"] = ""
    normalized["meta"]["cover_id"] = normalized["cover_id"]
    normalized["meta"]["image_file"] = normalized["file_name"]
    normalized["meta"]["performance_label"] = normalized["label"]
    return normalized


def failure_analysis(record: dict[str, Any], error: str) -> dict[str, Any]:
    failed = base_record(record)
    failed["error_summary"] = sanitize_error(error)
    failed["risk_notes"] = ["analysis_failed"]
    failed["qa_findings"]["revision_instruction"] = "Retry single-cover visual analysis."
    return failed


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_minimum_schema(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AnalysisError("analysis output is not a JSON object")
    required = [
        "cover_id",
        "source_path",
        "label",
        "status",
        "analysis_version",
        "image_level_observations",
        "decision_factors",
        "generation_strategy",
        "qa_findings",
        "reusable_prompt_signals",
        "risk_notes",
    ]
    missing = [key for key in required if key not in payload]
    if missing:
        raise AnalysisError("analysis output missing fields: " + ", ".join(missing))
    return payload


def find_codex_bin() -> str:
    configured = os.environ.get("TASK013_CODEX_BIN")
    if configured:
        return configured
    found = shutil.which("codex")
    if found:
        return found
    app_codex = "/Applications/Codex.app/Contents/Resources/codex"
    if Path(app_codex).exists():
        return app_codex
    raise AnalysisError("Codex CLI not found")


def first_stderr_line(stderr: str) -> str:
    for line in stderr.splitlines():
        stripped = line.strip()
        if stripped:
            return sanitize_error(stripped)[:240]
    return ""


def compress_with_pillow(src: Path, dst: Path) -> bool:
    try:
        from PIL import Image
    except Exception:
        return False

    with Image.open(src) as image:
        image = image.convert("RGB")
        image.thumbnail((1024, 1024))
        dst.parent.mkdir(parents=True, exist_ok=True)
        image.save(dst, format="JPEG", quality=70, optimize=True)
    return True


def compress_with_sips(src: Path, dst: Path) -> bool:
    sips = shutil.which("sips") or "/usr/bin/sips"
    if not Path(sips).exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            sips,
            "-s",
            "format",
            "jpeg",
            "-s",
            "formatOptions",
            "70",
            "-Z",
            "1024",
            str(src),
            "--out",
            str(dst),
        ],
        cwd=str(REPO_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0 and dst.exists()


def compress_runtime_image(record: dict[str, Any]) -> Path:
    src = Path(source_path(record))
    if not src.exists():
        raise AnalysisError(f"source image not found: {src}")
    dst = RUNTIME_IMAGE_DIR / f"{record['cover_id']}.jpg"
    if compress_with_pillow(src, dst):
        return dst
    if compress_with_sips(src, dst):
        return dst
    raise AnalysisError("Unable to compress image: Pillow and sips are unavailable or failed")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def build_codex_prompt(record: dict[str, Any], runtime_image: Path, output_file: Path) -> str:
    template = PROMPT_FILE.read_text(encoding="utf-8")
    cover_id = str(record.get("cover_id") or "")
    src = source_path(record)
    label = str(record.get("label") or "unknown")
    metadata = {
        "cover_id": cover_id,
        "source_path": src,
        "compressed_image_path": rel(runtime_image),
        "label": label,
        "analysis_version": ANALYSIS_VERSION,
        "output_json_path": rel(output_file),
    }
    failed_json = {
        "cover_id": cover_id,
        "source_path": src,
        "label": label,
        "status": "failed",
        "analysis_version": ANALYSIS_VERSION,
        "image_level_observations": {},
        "decision_factors": {},
        "generation_strategy": {},
        "qa_findings": {},
        "reusable_prompt_signals": [],
        "risk_notes": ["Codex CLI could not perform visual image analysis"],
        "error_summary": "Codex CLI could not perform visual image analysis",
    }
    return (
        template.strip()
        + "\n\n"
        + "当前只处理这一张压缩图。请读取 compressed_image_path 指向的本地图片，"
        + "不要读取其它图片，不要输出 base64，不要展示图片，不要调用外部 API。\n"
        + "最终回答只能输出一个 JSON object。不要输出“完成”。不要输出“success”作为自然语言。"
        + "不要输出 markdown。不要输出代码块。不要解释。不要写自然语言总结。"
        + "raw output 文件必须可以被 json.loads 直接解析。\n"
        + "脚本会把 raw output 解析后写入 output_json_path；你不要输出其它文本。\n\n"
        + "JSON 顶层字段必须包含: cover_id, source_path, label, status, analysis_version, "
        + "image_level_observations, decision_factors, generation_strategy, qa_findings, "
        + "reusable_prompt_signals, risk_notes。\n\n"
        + "如果无法真实视觉分析图片，也必须输出下面这种合法 JSON，不要编造视觉结论:\n"
        + json.dumps(failed_json, ensure_ascii=False, indent=2)
        + "\n\n"
        + "当前单图 metadata:\n"
        + json.dumps(metadata, ensure_ascii=False, indent=2)
        + "\n"
    )


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

    raise AnalysisError("raw Codex output was not a JSON object")


def run_codex_cli_backend(record: dict[str, Any], timeout: int) -> dict[str, Any]:
    output_file = cover_output_path(record)
    runtime_image = compress_runtime_image(record)
    prompt_text = build_codex_prompt(record, runtime_image, output_file)

    RUNTIME_PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    prompt_file = RUNTIME_PROMPT_DIR / f"{record['cover_id']}.md"
    prompt_file.write_text(prompt_text, encoding="utf-8")

    CODEX_RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_file = CODEX_RAW_DIR / f"{record['cover_id']}.txt"
    codex_bin = find_codex_bin()
    command = [
        codex_bin,
        "-a",
        "never",
        "exec",
        "--skip-git-repo-check",
        "-C",
        str(REPO_ROOT),
        "-o",
        rel(raw_file),
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
        stderr_line = first_stderr_line(result.stderr)
        message = f"Codex CLI failed exit_code={result.returncode}"
        if stderr_line:
            message += f"; stderr_first_line={stderr_line}"
        raise AnalysisError(message)
    if not raw_file.exists():
        raise AnalysisError("Codex CLI completed but did not write raw output")

    raw_text = raw_file.read_text(encoding="utf-8", errors="replace")
    payload = parse_json_object_from_text(raw_text)
    return normalize_analysis(record, validate_minimum_schema(payload))


def response_json_schema() -> dict[str, Any]:
    string = {"type": "string"}
    number = {"type": "number"}
    string_array = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "cover_id",
            "source_path",
            "file_name",
            "label",
            "analysis_version",
            "status",
            "analysis_status",
            "meta",
            "image_level_observations",
            "decision_factors",
            "generation_strategy",
            "qa_findings",
            "reusable_prompt_signals",
            "risk_notes",
            "error_summary",
        ],
        "properties": {
            "cover_id": string,
            "source_path": string,
            "file_name": string,
            "label": {"type": "string", "enum": ["satisfied", "unsatisfied", "unknown"]},
            "analysis_version": string,
            "status": {"type": "string", "enum": ["success", "failed"]},
            "analysis_status": {"type": "string", "enum": ["success", "failed"]},
            "meta": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "cover_id",
                    "image_file",
                    "video_type",
                    "publish_channel",
                    "performance_label",
                    "performance_metric",
                    "business_goal",
                ],
                "properties": {
                    "cover_id": string,
                    "image_file": string,
                    "video_type": string,
                    "publish_channel": string,
                    "performance_label": string,
                    "performance_metric": string,
                    "business_goal": string,
                },
            },
            "image_level_observations": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "primary_subject",
                    "visible_text_summary",
                    "visual_hierarchy",
                    "notable_design_elements",
                ],
                "properties": {
                    "primary_subject": string,
                    "visible_text_summary": string,
                    "visual_hierarchy": string,
                    "notable_design_elements": string_array,
                },
            },
            "decision_factors": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "scene_classification",
                    "frame_type",
                    "face_signal",
                    "emotion_signal",
                    "composition_signal",
                    "information_density",
                    "event_signal",
                    "product_visibility",
                    "title_hook_type",
                    "layout_type",
                    "click_logic",
                    "reusable_pattern",
                ],
                "properties": {
                    "scene_classification": string,
                    "frame_type": string,
                    "face_signal": number,
                    "emotion_signal": number,
                    "composition_signal": number,
                    "information_density": number,
                    "event_signal": number,
                    "product_visibility": string,
                    "title_hook_type": string_array,
                    "layout_type": string,
                    "click_logic": string,
                    "reusable_pattern": string,
                },
            },
            "generation_strategy": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "generation_mode",
                    "reference_frame_usage",
                    "subject_preservation",
                    "background_strategy",
                    "title_area_planning",
                    "brand_element_strategy",
                    "image2_prompt_direction",
                    "negative_constraints",
                    "generation_risk",
                ],
                "properties": {
                    "generation_mode": string,
                    "reference_frame_usage": string,
                    "subject_preservation": string,
                    "background_strategy": string,
                    "title_area_planning": string,
                    "brand_element_strategy": string,
                    "image2_prompt_direction": string,
                    "negative_constraints": string_array,
                    "generation_risk": string,
                },
            },
            "qa_findings": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "face_quality_check",
                    "product_accuracy_check",
                    "text_area_check",
                    "brand_consistency_check",
                    "clickability_check",
                    "platform_fit_check",
                    "ai_artifact_risk",
                    "final_usability",
                    "revision_instruction",
                ],
                "properties": {
                    "face_quality_check": string,
                    "product_accuracy_check": string,
                    "text_area_check": string,
                    "brand_consistency_check": string,
                    "clickability_check": string,
                    "platform_fit_check": string,
                    "ai_artifact_risk": string,
                    "final_usability": string,
                    "revision_instruction": string,
                },
            },
            "reusable_prompt_signals": string_array,
            "risk_notes": string_array,
            "error_summary": string,
        },
    }


def api_config() -> tuple[str, str, str]:
    api_key = (
        os.environ.get("TASK013_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("RBAPI_API_KEY")
    )
    if not api_key:
        raise AnalysisError("Missing vision API credentials")
    base_url = (
        os.environ.get("TASK013_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("RBAPI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = os.environ.get("TASK013_MODEL") or os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL
    return api_key, base_url, model


def api_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def read_api_error(exc: urllib.error.HTTPError) -> str:
    body = exc.read(2048).decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            error = parsed.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])
    except json.JSONDecodeError:
        pass
    return body or str(exc)


def request_json(
    method: str, url: str, api_key: str, payload: dict[str, Any] | None, timeout: int
) -> dict[str, Any]:
    data = None
    headers = {"Authorization": f"Bearer {api_key}"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise AnalysisError(read_api_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise AnalysisError(str(exc.reason)) from exc


def upload_file(path: Path, api_key: str, base_url: str, timeout: int) -> str:
    boundary = f"----task013-{uuid.uuid4().hex}"
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="purpose"\r\n\r\n')
    body.extend(b"vision\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    request = urllib.request.Request(
        api_url(base_url, "/files"),
        data=bytes(body),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise AnalysisError(read_api_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise AnalysisError(str(exc.reason)) from exc

    file_id = payload.get("id")
    if not file_id:
        raise AnalysisError("File upload response did not include a file id")
    return str(file_id)


def delete_uploaded_file(file_id: str, api_key: str, base_url: str, timeout: int) -> None:
    try:
        request_json("DELETE", api_url(base_url, f"/files/{file_id}"), api_key, None, timeout)
    except AnalysisError:
        pass


def extract_response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def parse_model_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:]
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise AnalysisError("Model output was not a JSON object")
    return parsed


def build_direct_api_prompt(record: dict[str, Any]) -> str:
    metadata = {
        "cover_id": record.get("cover_id"),
        "source_path": source_path(record),
        "file_name": record.get("file_name"),
        "label": record.get("label"),
        "analysis_version": ANALYSIS_VERSION,
    }
    return (
        PROMPT_FILE.read_text(encoding="utf-8").strip()
        + "\n\nCurrent cover metadata, for JSON identity fields only:\n"
        + json.dumps(metadata, ensure_ascii=False, indent=2)
    )


def run_direct_api_backend(
    record: dict[str, Any], timeout: int, keep_uploaded_file: bool
) -> dict[str, Any]:
    api_key, base_url, model = api_config()
    src = Path(source_path(record))
    if not src.exists():
        raise AnalysisError(f"Image file not found: {src}")

    file_id = upload_file(src, api_key, base_url, timeout)
    try:
        payload = {
            "model": model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": build_direct_api_prompt(record)},
                        {"type": "input_image", "file_id": file_id, "detail": "high"},
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "task013_cover_reverse_v2",
                    "strict": True,
                    "schema": response_json_schema(),
                }
            },
            "max_output_tokens": 5000,
        }
        response = request_json(
            "POST", api_url(base_url, "/responses"), api_key, payload, timeout
        )
    finally:
        if not keep_uploaded_file:
            delete_uploaded_file(file_id, api_key, base_url, min(timeout, 30))

    text = extract_response_text(response)
    if not text:
        raise AnalysisError("Responses API returned no output text")
    return normalize_analysis(record, validate_minimum_schema(parse_model_json(text)))


def analyze_one(
    record: dict[str, Any], backend: str, timeout: int, keep_uploaded_file: bool
) -> dict[str, Any]:
    if backend == "codex_cli":
        return run_codex_cli_backend(record, timeout)
    if backend == "direct_api":
        return run_direct_api_backend(record, timeout, keep_uploaded_file)
    raise AnalysisError(f"Unsupported backend: {backend}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze one task013 cover image.")
    parser.add_argument("--id", dest="cover_id", help="Example: cover_001")
    parser.add_argument("--cover-id", dest="cover_id_alias", help="Example: cover_001")
    parser.add_argument("--index", type=int, help="1-based manifest index, e.g. 1")
    parser.add_argument(
        "--backend",
        choices=["codex_cli", "direct_api"],
        default=DEFAULT_BACKEND,
        help="Default: codex_cli. direct_api is used only when explicitly requested.",
    )
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--keep-uploaded-file", action="store_true")
    args = parser.parse_args()

    try:
        manifest = load_manifest()
        cover_id = args.cover_id or args.cover_id_alias
        record = resolve_record(manifest, cover_id, args.index)
        out_file = cover_output_path(record)
    except Exception as exc:
        print(f"failed: {sanitize_error(str(exc))}", file=sys.stderr)
        return 1

    try:
        result = analyze_one(record, args.backend, args.timeout, args.keep_uploaded_file)
    except Exception as exc:
        result = failure_analysis(record, str(exc))

    write_json(out_file, result)
    print(f"wrote {rel(out_file)} status={result['status']} backend={args.backend}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
