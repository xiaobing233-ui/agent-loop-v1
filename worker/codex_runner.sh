#!/usr/bin/env bash

# codex_runner.sh
# 用法：
#   ./worker/codex_runner.sh <prompt文件路径> <task_id> [task_type] [task_json]
#
# 功能：
# 1. 接收 prompt 文件路径和 task_id
# 2. 如果本机有 codex CLI，就优先调用非交互模式执行
# 3. 如果本机没有 codex CLI，就使用 Python 标准库 fallback，并明确标记 status=fallback
# 4. 输出 v2 标准文件到 outputs/{task_id}/result.json、result.md、run.log

set -u

# 第一步：读取参数。
PROMPT_FILE="${1:-}"
TASK_ID="${2:-}"
TASK_TYPE="${3:-unknown}"
TASK_JSON="${4:-}"

# 第二步：定位项目根目录，也就是 agent-loop-v1/。
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 第三步：准备 Python 命令。可以通过 PYTHON_BIN 环境变量自定义。
PYTHON_BIN="${PYTHON_BIN:-python3}"

# 第四步：检查参数是否完整。
if [ -z "${PROMPT_FILE}" ] || [ -z "${TASK_ID}" ]; then
  echo "[codex_runner] 用法: $0 <prompt文件路径> <task_id>"
  exit 1
fi

# 第五步：创建当前 task 的输出目录。
OUTPUT_DIR="${ROOT_DIR}/outputs/${TASK_ID}"
OUTPUT_FILE="${OUTPUT_DIR}/output.txt"
RESULT_JSON="${OUTPUT_DIR}/result.json"
RESULT_MD="${OUTPUT_DIR}/result.md"
RUN_LOG="${OUTPUT_DIR}/run.log"
STARTED_AT="$(date "+%Y-%m-%dT%H:%M:%S")"
START_SECONDS="$(date "+%s")"
CODEX_EXEC_TIMEOUT_SECONDS="${CODEX_EXEC_TIMEOUT_SECONDS:-240}"
mkdir -p "${OUTPUT_DIR}"
: > "${RUN_LOG}"

log() {
  echo "[codex_runner] $*" | tee -a "${RUN_LOG}"
}

write_result_json() {
  # 使用 Python 标准库写 JSON，避免 bash 手写 JSON 转义出错。
  local status="$1"
  local runner="$2"
  local summary="$3"
  local error="${4:-}"

  if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    "${PYTHON_BIN}" - "${TASK_ID}" "${TASK_TYPE}" "${status}" "${runner}" "${STARTED_AT}" "${START_SECONDS}" "${ROOT_DIR}" "${OUTPUT_FILE}" "${RESULT_JSON}" "${RESULT_MD}" "${RUN_LOG}" "${summary}" "${error}" <<'PY'
import json
import sys
import time
from datetime import datetime
from pathlib import Path

task_id = sys.argv[1]
task_type = sys.argv[2]
status = sys.argv[3]
runner = sys.argv[4]
started_at = sys.argv[5]
start_seconds = float(sys.argv[6])
root_dir = Path(sys.argv[7])
output_file = Path(sys.argv[8])
result_json = Path(sys.argv[9])
result_md = Path(sys.argv[10])
run_log = Path(sys.argv[11])
summary = sys.argv[12]
error = sys.argv[13]

finished_at = datetime.now().isoformat(timespec="seconds")
duration_seconds = round(max(0, time.time() - start_seconds), 3)
log_text = run_log.read_text(encoding="utf-8") if run_log.exists() else ""


def relative(path):
    try:
        return str(path.relative_to(root_dir))
    except ValueError:
        return str(path)


known_files = [output_file, result_json, result_md, run_log]
known_files.extend(path for path in sorted(result_json.parent.glob("*")) if path.is_file())
output_files = []
seen = set()
for path in known_files:
    item = relative(path)
    if item not in seen:
        output_files.append(item)
        seen.add(item)

data = {
    "task_id": task_id,
    "type": task_type,
    "status": status,
    "runner": runner,
    "started_at": started_at,
    "finished_at": finished_at,
    "duration_seconds": duration_seconds,
    "summary": summary,
    "output_files": output_files,
    "error": error,
}

result_json.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

output_text = output_file.read_text(encoding="utf-8", errors="replace") if output_file.exists() else ""
result_md.write_text(
    "# Task " + task_id + "\n\n"
    "- Type: `" + task_type + "`\n"
    "- Status: `" + status + "`\n"
    "- Runner: `" + runner + "`\n"
    "- Started at: `" + started_at + "`\n"
    "- Finished at: `" + finished_at + "`\n"
    "- Duration: `" + str(duration_seconds) + "` seconds\n\n"
    "## Summary\n\n"
    + summary + "\n\n"
    + ("## Error\n\n" + error + "\n\n" if error else "")
    + "## Output\n\n```text\n"
    + output_text.rstrip()
    + "\n```\n\n"
    + "## Run Log\n\n```text\n"
    + log_text.rstrip()
    + "\n```\n",
    encoding="utf-8",
)
PY
  else
    # 极简兜底：如果连 Python 都没有，也尽量生成一个可读的 result.json。
    printf '{"task_id":"%s","type":"%s","status":"%s","runner":"%s","started_at":"%s","finished_at":"","duration_seconds":0,"summary":"%s","output_files":["%s"],"error":"%s"}\n' \
      "${TASK_ID}" "${TASK_TYPE}" "${status}" "${runner}" "${STARTED_AT}" "${summary}" "${OUTPUT_FILE}" "${error}" > "${RESULT_JSON}"
    {
      echo "# Task ${TASK_ID}"
      echo
      echo "- Type: \`${TASK_TYPE}\`"
      echo "- Status: \`${status}\`"
      echo "- Runner: \`${runner}\`"
      echo
      echo "${summary}"
    } > "${RESULT_MD}"
  fi
}

write_fallback_output() {
  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "未检测到 codex CLI，本次未真正执行 Codex，只生成 fallback 结果" > "${OUTPUT_FILE}"
    return 1
  fi

  "${PYTHON_BIN}" - "${PROMPT_FILE}" "${TASK_JSON}" "${OUTPUT_FILE}" "${TASK_ID}" "${TASK_TYPE}" >> "${RUN_LOG}" 2>&1 <<'PY'
import json
import re
import sys
from pathlib import Path

prompt_file = Path(sys.argv[1])
task_json_arg = sys.argv[2]
output_file = Path(sys.argv[3])
task_id_arg = sys.argv[4]
task_type_arg = sys.argv[5]


def load_task():
    if task_json_arg:
        task_path = Path(task_json_arg)
        if task_path.exists():
            return json.loads(task_path.read_text(encoding="utf-8"))

    prompt = prompt_file.read_text(encoding="utf-8", errors="replace")

    def section(name):
        pattern = rf"{re.escape(name)}:\n(.*?)(?=\n\n\S|$)"
        match = re.search(pattern, prompt, re.S)
        return match.group(1).strip() if match else ""

    task = {
        "id": section("任务 ID") or task_id_arg,
        "type": section("任务类型") or task_type_arg,
        "goal": section("任务目标"),
        "input": {},
        "constraints": {},
        "expected_outputs": [],
    }

    for key, label, fallback in [
        ("input", "输入", {}),
        ("constraints", "约束", {}),
        ("expected_outputs", "期望输出", []),
    ]:
        raw_value = section(label)
        try:
            task[key] = json.loads(raw_value) if raw_value else fallback
        except json.JSONDecodeError:
            task[key] = fallback

    return task


task = load_task()
task_id = str(task.get("id") or task_id_arg)
task_type = str(task.get("type") or task_type_arg)
goal = str(task.get("goal") or "")
input_data = task.get("input") if isinstance(task.get("input"), dict) else {}
constraints = task.get("constraints") if isinstance(task.get("constraints"), dict) else {}
expected_outputs = task.get("expected_outputs") if isinstance(task.get("expected_outputs"), list) else []
must_include = constraints.get("must_include", [])
if not isinstance(must_include, list):
    must_include = [str(must_include)]

lines = [
    "# Fallback 任务摘要",
    "",
    "> 未检测到 codex CLI，本次未真正执行 Codex，只生成 fallback 结果",
    "",
    "这不是 Codex 生成的最终业务结果，只是 fallback 摘要。它用于保留任务信息，方便安装或修复 Codex CLI 后重新执行。",
    "",
    "## 基本信息",
    "",
    f"- Task ID: `{task_id}`",
    f"- Task Type: `{task_type}`",
    "",
    "## Goal",
    "",
    goal or "未提供",
    "",
    "## Input Text",
    "",
    str(input_data.get("text") or "未提供"),
    "",
    "## Constraints Must Include",
    "",
]

if must_include:
    lines.extend(f"- {item}" for item in must_include)
else:
    lines.append("未提供")

lines.extend([
    "",
    "## Expected Outputs",
    "",
])

if expected_outputs:
    lines.extend(f"- `{item}`" for item in expected_outputs)
else:
    lines.append("未提供")

lines.extend([
    "",
    "## 原始约束",
    "",
    "```json",
    json.dumps(constraints, ensure_ascii=False, indent=2),
    "```",
    "",
    "## 下一步",
    "",
    "请确认本地已安装 codex CLI，并且运行 worker 的终端中 `command -v codex` 能找到该命令，然后重新提交或重新执行任务。",
    "",
])

output_file.write_text("\n".join(lines), encoding="utf-8")
print(f"python fallback wrote: {output_file}")
PY
}

find_codex_bin() {
  if command -v codex >/dev/null 2>&1; then
    command -v codex
    return 0
  fi

  local app_codex="/Applications/Codex.app/Contents/Resources/codex"
  if [ -x "${app_codex}" ]; then
    echo "${app_codex}"
    return 0
  fi

  return 1
}

codex_supports_exec() {
  "${CODEX_BIN}" exec --help 2>&1 | grep -qi "non-interactively"
}

run_codex_exec_with_timeout() {
  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    log "Python 不可用，无法为 Codex exec 提供 timeout 包装"
    echo "Python 不可用，无法为 Codex exec 提供 timeout 包装；未执行 Codex。" > "${OUTPUT_FILE}"
    return 1
  fi

  "${PYTHON_BIN}" - "${CODEX_BIN}" "${PROMPT_FILE}" "${OUTPUT_FILE}" "${RUN_LOG}" "${ROOT_DIR}" "${CODEX_EXEC_TIMEOUT_SECONDS}" >> "${RUN_LOG}" 2>&1 <<'PY'
from datetime import datetime
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

codex_bin = sys.argv[1]
prompt_file = Path(sys.argv[2])
output_file = Path(sys.argv[3])
run_log = Path(sys.argv[4])
root_dir = sys.argv[5]
timeout_seconds = int(sys.argv[6])

command = [
    codex_bin,
    "-a",
    "never",
    "exec",
    "--skip-git-repo-check",
    "--color",
    "never",
    "-s",
    "workspace-write",
    "-C",
    root_dir,
    "-o",
    str(output_file),
    "-",
]

exit_code = 1
timed_out = False
start_time = time.time()

with prompt_file.open("rb") as stdin_file, run_log.open("ab") as log_file:
    started_at = datetime.now().isoformat(timespec="seconds")
    log_file.write(f"codex exec started_at: {started_at}\n".encode("utf-8"))
    log_file.write(f"codex exec timeout_seconds: {timeout_seconds}\n".encode("utf-8"))
    log_file.write(("codex exec command: " + " ".join(command) + "\n").encode("utf-8"))
    log_file.flush()

    process = subprocess.Popen(
        command,
        stdin=stdin_file,
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
    )

    try:
        exit_code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        log_file.write(f"codex exec timed_out: yes\n".encode("utf-8"))
        log_file.write(f"codex exec sending SIGTERM to process group: {process.pid}\n".encode("utf-8"))
        log_file.flush()

        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            log_file.write("codex exec process group already exited before SIGTERM\n".encode("utf-8"))

        try:
            exit_code = process.wait(timeout=5)
            log_file.write(f"codex exec exited after SIGTERM: {exit_code}\n".encode("utf-8"))
        except subprocess.TimeoutExpired:
            log_file.write(f"codex exec sending SIGKILL to process group: {process.pid}\n".encode("utf-8"))
            log_file.flush()
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                log_file.write("codex exec process group already exited before SIGKILL\n".encode("utf-8"))
            exit_code = process.wait()
            log_file.write(f"codex exec exited after SIGKILL: {exit_code}\n".encode("utf-8"))

        output_file.write_text(
            f"Codex non-interactive execution timed out after {timeout_seconds} seconds.\n",
            encoding="utf-8",
        )
        exit_code = 124
    else:
        log_file.write("codex exec timed_out: no\n".encode("utf-8"))

    finished_at = datetime.now().isoformat(timespec="seconds")
    duration_seconds = round(time.time() - start_time, 3)
    log_file.write(f"codex exec finished_at: {finished_at}\n".encode("utf-8"))
    log_file.write(f"codex exec duration_seconds: {duration_seconds}\n".encode("utf-8"))
    log_file.write(f"codex exec exit_code: {exit_code}\n".encode("utf-8"))
    log_file.flush()

if not output_file.exists():
    output_file.write_text("", encoding="utf-8")

sys.exit(exit_code)
PY
}

# 第六步：检查 prompt 文件是否存在。
if [ ! -f "${PROMPT_FILE}" ]; then
  log "prompt 文件不存在: ${PROMPT_FILE}"
  echo "prompt 文件不存在: ${PROMPT_FILE}" > "${OUTPUT_FILE}"
  write_result_json "failed" "python_fallback" "prompt 文件不存在" "prompt 文件不存在: ${PROMPT_FILE}"
  exit 1
fi

log "开始执行 task: ${TASK_ID}"
log "type: ${TASK_TYPE}"
log "prompt: ${PROMPT_FILE}"
log "output: ${OUTPUT_FILE}"
log "result_json: ${RESULT_JSON}"
log "result_md: ${RESULT_MD}"
log "run_log: ${RUN_LOG}"
log "codex_exec_timeout_seconds: ${CODEX_EXEC_TIMEOUT_SECONDS}"
if [ -t 0 ]; then
  STDIN_TTY="yes"
else
  STDIN_TTY="no"
fi
if [ -t 1 ]; then
  STDOUT_TTY="yes"
else
  STDOUT_TTY="no"
fi
log "tty: stdin=${STDIN_TTY}, stdout=${STDOUT_TTY}, TERM=${TERM:-}"

# 第七步：如果安装了 codex CLI，就真实调用；否则使用 Python fallback。
if CODEX_BIN="$(find_codex_bin)"; then
  log "检测到 codex CLI: ${CODEX_BIN}"
  RUNNER="codex"

  if codex_supports_exec; then
    log "检测到 Codex 非交互子命令: exec，正在调用..."
    run_codex_exec_with_timeout
    CODEX_EXIT_CODE=$?
    if [ "${CODEX_EXIT_CODE}" -ne 0 ] && [ ! -s "${OUTPUT_FILE}" ]; then
      echo "Codex non-interactive execution failed; see run.log." > "${OUTPUT_FILE}"
    fi
  else
    log "Codex CLI 可用，但未发现非交互执行模式；不会启动交互 TUI"
    {
      echo "Codex CLI is available but no non-interactive execution mode was found."
      echo
      echo "Codex appears to require an interactive TTY/TUI; worker runs without TTY."
      echo "stdin_tty=${STDIN_TTY}"
      echo "stdout_tty=${STDOUT_TTY}"
      echo "TERM=${TERM:-}"
    } > "${OUTPUT_FILE}"
    CODEX_EXIT_CODE=1
    CODEX_FAILURE_KIND="no_noninteractive"
  fi
else
  log "未检测到 codex CLI，本次未真正执行 Codex，只生成 fallback 结果"
  write_fallback_output
  CODEX_EXIT_CODE=$?
  RUNNER="python_fallback"
fi

# 第八步：根据退出码写入结构化 result.json。
if [ "${RUNNER}" = "python_fallback" ] && [ "${CODEX_EXIT_CODE}" -eq 0 ]; then
  STATUS="fallback"
  SUMMARY="未检测到 codex CLI，未真正调用 Codex，仅生成兜底结果"
  ERROR=""
elif [ "${CODEX_EXIT_CODE}" -eq 0 ]; then
  STATUS="success"
  SUMMARY="Codex non-interactive execution completed"
  ERROR=""
elif [ "${RUNNER}" = "codex" ] && [ "${CODEX_FAILURE_KIND:-}" = "no_noninteractive" ]; then
  STATUS="failed"
  SUMMARY="Codex CLI is available but no non-interactive execution mode was found"
  ERROR="Codex appears to require an interactive TTY/TUI; worker runs without TTY"
elif [ "${RUNNER}" = "python_fallback" ]; then
  STATUS="failed"
  SUMMARY="Python fallback execution failed"
  ERROR="python fallback exit_code=${CODEX_EXIT_CODE}"
else
  STATUS="failed"
  SUMMARY="Codex non-interactive execution failed"
  ERROR="codex exec exit_code=${CODEX_EXIT_CODE}"
fi

log "执行结束，status=${STATUS}, exit_code=${CODEX_EXIT_CODE}"
log "最终 result status=${STATUS}, runner=${RUNNER}, exit_code=${CODEX_EXIT_CODE}"
write_result_json "${STATUS}" "${RUNNER}" "${SUMMARY}" "${ERROR}"

if [ "${STATUS}" = "fallback" ]; then
  exit 0
fi

exit "${CODEX_EXIT_CODE}"
