#!/usr/bin/env bash

# diagnose_codex.sh
# 用法：
#   bash worker/diagnose_codex.sh
#
# 只输出诊断信息，不修改项目文件。

set -u

APP_CODEX="/Applications/Codex.app/Contents/Resources/codex"

find_codex_bin() {
  if command -v codex >/dev/null 2>&1; then
    command -v codex
    return 0
  fi

  if [ -x "${APP_CODEX}" ]; then
    echo "${APP_CODEX}"
    return 0
  fi

  return 1
}

print_tty_state() {
  if [ -t 0 ]; then
    echo "stdin_tty: yes"
  else
    echo "stdin_tty: no"
  fi

  if [ -t 1 ]; then
    echo "stdout_tty: yes"
  else
    echo "stdout_tty: no"
  fi

  echo "TERM: ${TERM:-}"
}

echo "== Codex path =="
if CODEX_BIN="$(find_codex_bin)"; then
  echo "codex: ${CODEX_BIN}"
else
  echo "codex: not found"
  echo
  echo "diagnosis: no codex CLI found; worker would use python_fallback"
  exit 0
fi

echo
echo "== TTY =="
print_tty_state

MAIN_HELP="$("${CODEX_BIN}" --help 2>&1)"
EXEC_HELP="$("${CODEX_BIN}" exec --help 2>&1)"
RUN_HELP="$("${CODEX_BIN}" run --help 2>&1)"

echo
echo "== codex --help summary =="
printf '%s\n' "${MAIN_HELP}" | sed -n '1,80p'

echo
echo "== codex exec --help summary =="
printf '%s\n' "${EXEC_HELP}" | sed -n '1,80p'

echo
echo "== codex run --help summary =="
printf '%s\n' "${RUN_HELP}" | sed -n '1,40p'

echo
echo "== diagnosis =="
if printf '%s\n' "${EXEC_HELP}" | grep -qi "Run Codex non-interactively"; then
  echo "non_interactive_command: codex exec"
  echo "worker_call: codex -a never exec --skip-git-repo-check --color never -s workspace-write -C <repo> -o <output_file> -"
else
  echo "non_interactive_command: not found"
  echo "worker_call: unavailable; direct TUI launch should be treated as failed in worker"
fi

if printf '%s\n' "${MAIN_HELP}" | grep -q "If no subcommand is specified"; then
  echo "default_mode: interactive TUI when no subcommand is specified"
else
  echo "default_mode: unknown"
fi
