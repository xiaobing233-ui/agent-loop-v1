#!/usr/bin/env bash

# codex_runner.sh
# 用法：
#   ./worker/codex_runner.sh <prompt文件路径> <task_id>
#
# 功能：
# 1. 接收 prompt 文件路径和 task_id
# 2. 如果本机有 codex CLI，就调用 codex 执行
# 3. 如果本机没有 codex CLI，就使用 Python 标准库 fallback
# 4. 输出结构化结果到 outputs/{task_id}/result.json

set -u

# 第一步：读取参数。
PROMPT_FILE="${1:-}"
TASK_ID="${2:-}"

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
RUNNER_LOG="${OUTPUT_DIR}/runner.log"
mkdir -p "${OUTPUT_DIR}"
: > "${RUNNER_LOG}"

log() {
  echo "[codex_runner] $*" | tee -a "${RUNNER_LOG}"
}

write_result_json() {
  # 使用 Python 标准库写 JSON，避免 bash 手写 JSON 转义出错。
  local status="$1"

  if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    "${PYTHON_BIN}" - "${TASK_ID}" "${status}" "${OUTPUT_FILE}" "${RESULT_JSON}" "${RUNNER_LOG}" <<'PY'
import json
import sys
from pathlib import Path

task_id = sys.argv[1]
status = sys.argv[2]
output_file = Path(sys.argv[3])
result_json = Path(sys.argv[4])
runner_log = Path(sys.argv[5])

log_text = runner_log.read_text(encoding="utf-8") if runner_log.exists() else ""

data = {
    "task_id": task_id,
    "status": status,
    "output_file": str(output_file),
    "log": log_text,
}

result_json.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
  else
    # 极简兜底：如果连 Python 都没有，也尽量生成一个可读的 result.json。
    printf '{"task_id":"%s","status":"%s","output_file":"%s","log":"python unavailable; see runner.log"}\n' \
      "${TASK_ID}" "${status}" "${OUTPUT_FILE}" > "${RESULT_JSON}"
  fi
}

# 第六步：检查 prompt 文件是否存在。
if [ ! -f "${PROMPT_FILE}" ]; then
  log "prompt 文件不存在: ${PROMPT_FILE}"
  echo "prompt 文件不存在: ${PROMPT_FILE}" > "${OUTPUT_FILE}"
  write_result_json "failed"
  exit 1
fi

log "开始执行 task: ${TASK_ID}"
log "prompt: ${PROMPT_FILE}"
log "output: ${OUTPUT_FILE}"
log "result_json: ${RESULT_JSON}"

# 第七步：如果安装了 codex CLI，就真实调用；否则使用 Python fallback。
if command -v codex >/dev/null 2>&1; then
  log "检测到 codex CLI，正在调用..."

  # 这里使用 prompt 文件内容作为 Codex 输入，并把结果写入 output.txt。
  # 如果你的 codex CLI 参数不同，可以只调整这一行。
  codex "$(cat "${PROMPT_FILE}")" > "${OUTPUT_FILE}" 2>> "${RUNNER_LOG}"
  CODEX_EXIT_CODE=$?
else
  log "未检测到 codex CLI，使用 Python fallback 执行简单脚本..."

  if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    "${PYTHON_BIN}" - "${PROMPT_FILE}" "${OUTPUT_DIR}" "${OUTPUT_FILE}" >> "${RUNNER_LOG}" 2>&1 <<'PY'
import sys
from pathlib import Path

prompt_file = Path(sys.argv[1])
output_dir = Path(sys.argv[2])
output_file = Path(sys.argv[3])

prompt = prompt_file.read_text(encoding="utf-8")
output_dir.mkdir(parents=True, exist_ok=True)

# 这是 fallback 的简单可执行逻辑：
# 如果任务提到 CSV 和平均值，就生成一个只依赖标准库的 csv_average.py。
if "CSV" in prompt or "csv" in prompt:
    script_path = output_dir / "csv_average.py"
    script_path.write_text(
        '''#!/usr/bin/env python3
import csv
import sys


def parse_number(value):
    try:
        return float(value)
    except ValueError:
        return None


def main():
    if len(sys.argv) < 2:
        print("用法: python3 csv_average.py <csv文件路径> [列名]")
        sys.exit(1)

    csv_path = sys.argv[1]
    target_column = sys.argv[2] if len(sys.argv) >= 3 else None
    numbers = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            values = [row.get(target_column, "")] if target_column else row.values()
            for value in values:
                number = parse_number(str(value).strip())
                if number is not None:
                    numbers.append(number)

    if not numbers:
        print("没有找到可计算的数字")
        sys.exit(1)

    average = sum(numbers) / len(numbers)
    print(f"平均值: {average}")


if __name__ == "__main__":
    main()
''',
        encoding="utf-8",
    )

    output_file.write_text(
        "Python fallback 已生成脚本:\n"
        f"{script_path}\n\n"
        "运行示例:\n"
        f"python3 {script_path} data.csv amount\n",
        encoding="utf-8",
    )
else:
    output_file.write_text(
        "Python fallback 已执行。\n\n收到的 prompt 内容如下：\n"
        "----------------------------------------\n"
        f"{prompt}\n"
        "----------------------------------------\n",
        encoding="utf-8",
    )

print(f"python fallback wrote: {output_file}")
PY
    CODEX_EXIT_CODE=$?
  else
    log "codex CLI 不可用，Python fallback 也不可用"
    echo "codex CLI 不可用，Python fallback 也不可用" > "${OUTPUT_FILE}"
    CODEX_EXIT_CODE=1
  fi
fi

# 第八步：根据退出码写入结构化 result.json。
if [ "${CODEX_EXIT_CODE}" -eq 0 ]; then
  STATUS="success"
else
  STATUS="failed"
fi

log "执行结束，status=${STATUS}, exit_code=${CODEX_EXIT_CODE}"
write_result_json "${STATUS}"
exit "${CODEX_EXIT_CODE}"
