#!/usr/bin/env python3
"""
agent-loop-v1 GitHub-driven worker

完整闭环：
1. GitHub 仓库是唯一任务源
2. 启动时检查 git repo、origin、main 分支
3. 启动时和每轮循环开始前执行 git pull origin main
4. 只扫描 tasks/pending/ 中由 GitHub pull 下来的任务
5. 执行任务并生成 outputs/{task_id}/result.json
6. 每轮循环结束后执行 git add、git commit、git push
"""

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# 项目根目录：agent-loop-v1/
ROOT_DIR = Path(__file__).resolve().parents[1]

# 任务目录。pending 是 GitHub 任务来源，worker 不在本地自动创建任务文件。
PENDING_DIR = ROOT_DIR / "tasks" / "pending"
RUNNING_DIR = ROOT_DIR / "tasks" / "running"
DONE_DIR = ROOT_DIR / "tasks" / "done"
FAILED_DIR = ROOT_DIR / "tasks" / "failed"

# 输出、日志和 runner 脚本。
OUTPUTS_DIR = ROOT_DIR / "outputs"
LOGS_DIR = ROOT_DIR / "logs"
CONFLICT_BACKUP_DIR = LOGS_DIR / "conflict_backup"
SYSTEM_LOG = LOGS_DIR / "system.log"
CODEX_RUNNER = ROOT_DIR / "worker" / "codex_runner.sh"

# 基础配置。
SCAN_INTERVAL_SECONDS = 3
TASK_TIMEOUT_SECONDS = 300
GIT_REMOTE = "origin"
GIT_BRANCH = "main"
GIT_COMMIT_MESSAGE = "auto sync task results"
GIT_RETRIES = 3

# 默认使用系统 git；如果你的 git 不在 PATH，可以设置环境变量 GIT_BIN。
GIT_BIN = os.environ.get("GIT_BIN", "git")


@dataclass
class CommandResult:
    """保存 subprocess 执行结果，方便统一记录日志。"""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def now_text():
    """生成适合日志阅读的本地时间字符串。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def timestamp_for_path():
    """生成适合文件夹名的时间戳。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def log(message):
    """同时输出到 terminal 和 logs/system.log。"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{now_text()} [agent] {message}"
    print(line, flush=True)

    with SYSTEM_LOG.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def ensure_directories():
    """确保运行所需目录都存在，但不生成任何 pending task。"""
    for directory in [
        PENDING_DIR,
        RUNNING_DIR,
        DONE_DIR,
        FAILED_DIR,
        OUTPUTS_DIR,
        LOGS_DIR,
        CONFLICT_BACKUP_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def normalize_output(value):
    """subprocess 超时时偶尔会返回 bytes，这里统一成 str。"""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_command(command, label, timeout=None):
    """用 subprocess 执行命令，并把 stdout/stderr 记录到 terminal 和 system.log。"""
    log(f"运行命令: {label}: {' '.join(command)}")

    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT_DIR),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        message = f"命令不存在: {command[0]}，错误: {error}"
        log(message)
        return CommandResult(127, "", message)
    except subprocess.TimeoutExpired as error:
        stdout = normalize_output(error.stdout)
        stderr = normalize_output(error.stderr)
        message = f"命令超时: {label}, timeout={timeout}s"
        log(message)
        if stdout.strip():
            log(f"{label} stdout:\n{stdout.rstrip()}")
        if stderr.strip():
            log(f"{label} stderr:\n{stderr.rstrip()}")
        return CommandResult(124, stdout, stderr or message, timed_out=True)

    stdout = normalize_output(result.stdout)
    stderr = normalize_output(result.stderr)

    if stdout.strip():
        log(f"{label} stdout:\n{stdout.rstrip()}")
    if stderr.strip():
        log(f"{label} stderr:\n{stderr.rstrip()}")

    log(f"命令结束: {label}, exit_code={result.returncode}")
    return CommandResult(result.returncode, stdout, stderr)


def run_git(args, label):
    """统一执行 git 命令，方便替换 GIT_BIN。"""
    return run_command([GIT_BIN] + args, label=label)


def check_git_ready():
    """启动前检查当前目录是否已经正确绑定 GitHub 仓库。"""
    repo_result = run_git(["rev-parse", "--is-inside-work-tree"], "git repo check")
    if repo_result.returncode != 0 or repo_result.stdout.strip() != "true":
        log("启动失败: 当前目录不是 git repo。请先运行: git init")
        return False

    remote_result = run_git(["remote", "get-url", GIT_REMOTE], "git origin check")
    if remote_result.returncode != 0 or not remote_result.stdout.strip():
        log(
            "启动失败: 未设置 origin。请先运行: "
            "git remote add origin <YOUR_GITHUB_REPO_URL>"
        )
        return False

    branch_result = run_git(["branch", "--show-current"], "git branch check")
    current_branch = branch_result.stdout.strip()
    if branch_result.returncode != 0 or current_branch != GIT_BRANCH:
        log(
            f"启动失败: 当前分支是 '{current_branch or 'unknown'}'，"
            f"请切换到 {GIT_BRANCH}: git branch -M {GIT_BRANCH}"
        )
        return False

    log("git状态: 仓库检查通过，origin/main 已就绪")
    return True


def list_conflicted_files():
    """列出当前 git 冲突文件。"""
    result = run_git(["diff", "--name-only", "--diff-filter=U"], "git conflict list")
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def backup_conflict_ours(file_path, backup_root):
    """把冲突文件的本地版本备份到 logs/conflict_backup/。"""
    backup_path = backup_root / file_path
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    # :2: 是 git 冲突中的 ours，也就是本地版本。
    result = subprocess.run(
        [GIT_BIN, "show", f":2:{file_path}"],
        cwd=str(ROOT_DIR),
        capture_output=True,
    )

    if result.returncode == 0:
        backup_path.write_bytes(result.stdout)
        log(f"冲突备份: 已保存本地版本 {file_path} -> {backup_path}")
        return True

    # 如果 ours 不存在，退回到备份当前工作区文件。
    worktree_path = ROOT_DIR / file_path
    if worktree_path.exists():
        shutil.copy2(worktree_path, backup_path)
        log(f"冲突备份: 已保存工作区版本 {file_path} -> {backup_path}")
        return True

    log(f"冲突备份: 本地版本不存在，跳过备份 {file_path}")
    return False


def git_stage_exists(file_path, stage):
    """判断冲突索引中某个 stage 是否存在。stage 2 是本地，stage 3 是远端。"""
    result = subprocess.run(
        [GIT_BIN, "show", f":{stage}:{file_path}"],
        cwd=str(ROOT_DIR),
        capture_output=True,
    )
    return result.returncode == 0


def resolve_pull_conflicts_keep_remote():
    """发生 pull 冲突时，备份本地版本并自动保留 GitHub 远端版本。"""
    conflicted_files = list_conflicted_files()
    if not conflicted_files:
        log("冲突处理: 未发现 unmerged 文件，无法自动处理")
        return False

    backup_root = CONFLICT_BACKUP_DIR / timestamp_for_path()
    backup_root.mkdir(parents=True, exist_ok=True)
    log(f"冲突处理: GitHub 版本优先，本地冲突文件备份到 {backup_root}")

    for file_path in conflicted_files:
        backup_conflict_ours(file_path, backup_root)

        # --theirs 是 pull 进来的 GitHub 版本；如果远端删除了文件，就按远端删除。
        if git_stage_exists(file_path, 3):
            checkout_result = run_git(
                ["checkout", "--theirs", "--", file_path],
                f"keep remote version {file_path}",
            )
        else:
            checkout_result = run_git(
                ["rm", "-f", "--", file_path],
                f"keep remote deletion {file_path}",
            )

        add_result = run_git(["add", "-A", "--", file_path], f"stage {file_path}")

        if checkout_result.returncode != 0 or add_result.returncode != 0:
            log(f"冲突处理: 文件处理失败 {file_path}")
            return False

    commit_result = run_git(
        ["commit", "-m", "resolve pull conflict keep remote"],
        "git conflict commit",
    )
    if commit_result.returncode != 0:
        combined_output = f"{commit_result.stdout}\n{commit_result.stderr}"
        if "nothing to commit" not in combined_output:
            log("冲突处理: 自动提交冲突解决结果失败")
            return False

    log("冲突处理: 已保留 GitHub 版本并完成本地备份")
    return True


def output_mentions_conflict(result):
    """根据 git 输出判断是否像 pull 冲突。"""
    combined = f"{result.stdout}\n{result.stderr}".lower()
    conflict_words = [
        "conflict",
        "unmerged",
        "would be overwritten",
        "automatic merge failed",
    ]
    return any(word in combined for word in conflict_words)


def parse_overwritten_files(result):
    """解析 git pull 输出中会被远端覆盖的本地文件列表。"""
    files = []
    capture = False
    combined = f"{result.stdout}\n{result.stderr}"

    for line in combined.splitlines():
        stripped = line.strip()
        if "would be overwritten by merge" in stripped:
            capture = True
            continue

        if not capture:
            continue

        if not stripped or stripped.startswith("Please ") or stripped == "Aborting":
            capture = False
            continue

        if stripped.startswith("error:"):
            continue

        files.append(stripped)

    return files


def backup_worktree_file(file_path, backup_root):
    """把普通工作区文件备份到 logs/conflict_backup/。"""
    source_path = ROOT_DIR / file_path
    backup_path = backup_root / file_path
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        log(f"冲突备份: 工作区文件不存在，跳过 {file_path}")
        return False

    if source_path.is_file():
        shutil.copy2(source_path, backup_path)
        log(f"冲突备份: 已保存工作区文件 {file_path} -> {backup_path}")
        return True

    if source_path.is_dir():
        shutil.copytree(source_path, backup_path, dirs_exist_ok=True)
        log(f"冲突备份: 已保存工作区目录 {file_path} -> {backup_path}")
        return True

    log(f"冲突备份: 不支持的文件类型，跳过 {file_path}")
    return False


def backup_and_discard_overwritten_files(file_paths):
    """备份会被远端覆盖的本地文件，并清理本地版本以便重新 pull。"""
    if not file_paths:
        return False

    backup_root = CONFLICT_BACKUP_DIR / timestamp_for_path()
    backup_root.mkdir(parents=True, exist_ok=True)
    log(f"冲突处理: 本地文件将被 GitHub 覆盖，先备份到 {backup_root}")

    for file_path in file_paths:
        backup_worktree_file(file_path, backup_root)

        # tracked 文件用 checkout 丢弃本地修改；untracked 文件备份后删除。
        checkout_result = run_git(
            ["checkout", "--", file_path],
            f"discard local change {file_path}",
        )
        if checkout_result.returncode != 0:
            local_path = ROOT_DIR / file_path
            if local_path.is_file():
                local_path.unlink()
                log(f"冲突处理: 已删除本地未跟踪文件 {file_path}")
            elif local_path.is_dir():
                shutil.rmtree(local_path)
                log(f"冲突处理: 已删除本地未跟踪目录 {file_path}")

    return True


def git_pull(reason):
    """从 GitHub 拉取远程任务；失败时重试 3 次，冲突时远端优先。"""
    log(f"git状态: 开始 pull，原因={reason}")

    for attempt in range(1, GIT_RETRIES + 1):
        result = run_git(
            ["pull", "--no-rebase", GIT_REMOTE, GIT_BRANCH],
            f"git pull attempt {attempt}",
        )

        if result.returncode == 0:
            log(f"git状态: pull 成功，attempt={attempt}")
            return True

        log(f"git状态: pull 失败，attempt={attempt}/{GIT_RETRIES}")

        overwritten_files = parse_overwritten_files(result)
        if overwritten_files and backup_and_discard_overwritten_files(overwritten_files):
            log("git状态: 已备份并清理会被远端覆盖的本地文件，准备重试 pull")
            continue

        if output_mentions_conflict(result) or list_conflicted_files():
            log("git状态: 检测到 pull 冲突，开始自动保留 GitHub 版本")
            if resolve_pull_conflicts_keep_remote():
                return True

        if attempt < GIT_RETRIES:
            time.sleep(2)

    log("git状态: pull 重试 3 次后仍失败，本轮不会执行 Codex")
    return False


def git_status_short():
    """读取 git status --short，用于日志和判断是否需要 commit。"""
    result = run_git(["status", "--short"], "git status")

    if result.returncode != 0:
        log("git状态: 无法读取 status")
        return None

    status = result.stdout.strip()
    log(f"git状态: {'clean' if not status else status}")
    return status


def git_push_with_retry():
    """推送到 GitHub；失败时自动重试 3 次。"""
    for attempt in range(1, GIT_RETRIES + 1):
        push_result = run_git(
            ["push", GIT_REMOTE, GIT_BRANCH],
            f"git push attempt {attempt}",
        )

        if push_result.returncode == 0:
            log(f"git状态: push 成功，attempt={attempt}")
            return True

        log(f"git状态: push 失败，attempt={attempt}/{GIT_RETRIES}")
        if attempt < GIT_RETRIES:
            time.sleep(2)

    log("git状态: push 重试 3 次后仍失败")
    return False


def git_commit_and_push():
    """每轮 loop 结束后执行 git add、commit、push，把结果回写 GitHub。"""
    log("git状态: 开始 add/commit/push")

    add_result = run_git(["add", "."], "git add")
    if add_result.returncode != 0:
        log("git状态: git add 失败，跳过本轮 commit/push")
        return False

    status = git_status_short()
    if status is None:
        log("git状态: status 失败，跳过本轮 commit/push")
        return False

    if status:
        commit_result = run_git(
            ["commit", "-m", GIT_COMMIT_MESSAGE],
            "git commit",
        )
        if commit_result.returncode != 0:
            combined_output = f"{commit_result.stdout}\n{commit_result.stderr}"
            if "nothing to commit" not in combined_output:
                log("git状态: git commit 失败，跳过本轮 push")
                return False
    else:
        log("git状态: 没有文件变化，跳过 commit，但仍执行 push 检查远端同步")

    return git_push_with_retry()


def sync_results_to_github(processed_task_count):
    """只有本轮真正处理过任务时，才把结果同步回 GitHub。"""
    if processed_task_count <= 0:
        log("本轮没有处理任务，跳过 git add/commit/push")
        return True

    log(f"本轮处理任务数 > 0，开始同步结果: {processed_task_count}")
    return git_commit_and_push()


def iso_now():
    """生成适合 result.json 的时间字符串。"""
    return datetime.now().isoformat(timespec="seconds")


def load_task(task_path):
    """读取并解析 JSON task 文件。"""
    with task_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize_task(task, task_path):
    """兼容旧 task，并把它转换成 v2 标准字段。"""
    task_id = str(task.get("id") or task_path.stem)
    task_type = str(task.get("type") or "code_task")
    goal = str(task.get("goal") or "")
    input_data = task.get("input") if isinstance(task.get("input"), dict) else {}
    constraints = task.get("constraints") if isinstance(task.get("constraints"), dict) else {}

    normalized_input = dict(input_data)
    normalized_input["files"] = input_data.get("files", [])
    normalized_input["text"] = str(input_data.get("text", ""))

    normalized_constraints = dict(constraints)
    normalized_constraints["language"] = constraints.get("language", "zh-CN")
    normalized_constraints["output_format"] = constraints.get(
        "output_format",
        "markdown + json",
    )
    normalized_constraints["dependencies"] = constraints.get(
        "dependencies",
        "只使用必要依赖",
    )

    expected_outputs = task.get("expected_outputs")
    if not isinstance(expected_outputs, list) or not expected_outputs:
        expected_outputs = [
            f"outputs/{task_id}/result.md",
            f"outputs/{task_id}/result.json",
        ]

    return {
        "id": task_id,
        "type": task_type,
        "goal": goal,
        "input": normalized_input,
        "constraints": normalized_constraints,
        "expected_outputs": [str(item) for item in expected_outputs],
        "status": str(task.get("status") or "pending"),
        "raw": task,
    }


def build_prompt(task):
    """把 v2 task 转换成 Codex CLI 可以理解的 prompt 文本。"""
    return f"""你是本地 Codex 自动执行系统中的执行助手。

任务 ID:
{task["id"]}

任务类型:
{task["type"]}

任务目标:
{task["goal"]}

输入:
{json.dumps(task["input"], ensure_ascii=False, indent=2)}

约束:
{json.dumps(task["constraints"], ensure_ascii=False, indent=2)}

期望输出:
{json.dumps(task["expected_outputs"], ensure_ascii=False, indent=2)}

请根据任务目标完成工作。输出应便于写入 result.md，并尽量给出清晰、可复用的结果。
"""


def task_output_dir(task_id):
    """返回某个任务的输出目录，并保证目录存在。"""
    output_dir = OUTPUTS_DIR / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def result_json_path(task_id):
    """返回 v2 result.json 路径。"""
    return task_output_dir(task_id) / "result.json"


def result_md_path(task_id):
    """返回 v2 result.md 路径。"""
    return task_output_dir(task_id) / "result.md"


def run_log_path(task_id):
    """返回 v2 run.log 路径。"""
    return task_output_dir(task_id) / "run.log"


def append_run_log(task_id, message):
    """向 outputs/{task_id}/run.log 追加执行日志。"""
    line = f"{now_text()} [agent] {message}"
    with run_log_path(task_id).open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def write_prompt_file(task):
    """为当前任务生成 prompt 文件，交给 codex_runner.sh 使用。"""
    prompt_path = task_output_dir(task["id"]) / "prompt.txt"
    prompt_path.write_text(build_prompt(task), encoding="utf-8")
    return prompt_path


def relative_path(path):
    """输出相对项目根目录的路径，方便 GitHub 页面阅读。"""
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def collect_output_files(task_id):
    """收集当前任务输出目录中的文件列表。"""
    output_dir = task_output_dir(task_id)
    return [
        relative_path(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file()
    ]


def read_text_if_exists(path, limit=4000):
    """读取文本文件并截断，防止 result.md 过长。"""
    if not path.exists():
        return ""

    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > limit:
        return text[:limit] + "\n\n... output truncated ...\n"
    return text


def make_summary(task, status, error=""):
    """生成 result.json 中的短摘要。"""
    if status == "success":
        return f"{task['type']} completed: {task['goal']}"
    if status == "fallback":
        return "未检测到 codex CLI，未真正调用 Codex，仅生成兜底结果"
    return f"{task['type']} failed: {error or task['goal']}"


def write_result_files(task, status, started_at, started_time, error="", runner="codex"):
    """统一写入 v2 标准结果文件：result.json、result.md、run.log。"""
    task_id = task["id"]
    finished_at = iso_now()
    duration_seconds = round(time.time() - started_time, 3)
    summary = make_summary(task, status, error)
    output_text = read_text_if_exists(task_output_dir(task_id) / "output.txt")

    append_run_log(
        task_id,
        f"finish status={status} duration_seconds={duration_seconds} error={error}",
    )

    output_files = collect_output_files(task_id)
    result_data = {
        "task_id": task_id,
        "type": task["type"],
        "status": status,
        "runner": runner,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "summary": summary,
        "output_files": output_files,
        "error": error,
    }

    result_json_path(task_id).write_text(
        json.dumps(result_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md_lines = [
        f"# Task {task_id}",
        "",
        f"- Type: `{task['type']}`",
        f"- Status: `{status}`",
        f"- Runner: `{runner}`",
        f"- Started at: `{started_at}`",
        f"- Finished at: `{finished_at}`",
        f"- Duration: `{duration_seconds}` seconds",
        "",
        "## Goal",
        "",
        task["goal"],
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Output Files",
        "",
    ]

    md_lines.extend([f"- `{item}`" for item in collect_output_files(task_id)])

    if error:
        md_lines.extend(["", "## Error", "", error])

    if output_text.strip():
        md_lines.extend(["", "## Runner Output", "", "```text", output_text.rstrip(), "```"])

    result_md_path(task_id).write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    log(f"v2结果已写入: {result_json_path(task_id)} 和 {result_md_path(task_id)}")
    return result_data


def move_task(source_path, target_dir):
    """把任务文件移动到指定目录，保持原文件名不变。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / source_path.name

    # 如果目标文件已存在，追加时间戳，避免覆盖旧结果。
    if target_path.exists():
        timestamp = int(time.time())
        target_path = target_dir / f"{source_path.stem}_{timestamp}{source_path.suffix}"

    shutil.move(str(source_path), str(target_path))
    return target_path


def result_is_success(task_id):
    """判断 outputs/{task_id}/result.json 是否已经成功，防止重复执行。"""
    path = result_json_path(task_id)
    if not path.exists():
        return False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False

    return data.get("status") == "success"


def should_skip_task(task, pending_path):
    """防重复执行；返回 archived_duplicate、running 或空字符串。"""
    task_id = task["id"]
    done_path = DONE_DIR / pending_path.name
    running_path = RUNNING_DIR / pending_path.name

    if done_path.exists():
        log(f"跳过重复任务: tasks/done 已存在 {pending_path.name}")
        move_task(pending_path, DONE_DIR)
        return "archived_duplicate"

    if result_is_success(task_id):
        log(f"跳过重复任务: outputs/{task_id}/result.json 已是 success")
        move_task(pending_path, DONE_DIR)
        return "archived_duplicate"

    if running_path.exists():
        log(f"跳过任务: tasks/running 已存在 {pending_path.name}")
        return "running"

    return ""


def read_runner_status(task_id):
    """读取 runner 生成的 result.json 状态和执行器类型。"""
    path = result_json_path(task_id)
    if not path.exists():
        return "failed", "codex", f"result.json 不存在: {path}"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return "failed", "codex", f"result.json 解析失败: {error}"

    status = str(data.get("status", "failed"))
    runner = str(data.get("runner") or "codex")
    error = str(data.get("error", ""))
    summary = str(data.get("summary", ""))
    return status, runner, error or summary


def run_codex(prompt_path, task, task_path):
    """使用 subprocess 调用 codex_runner.sh，并设置单任务 60 秒超时。"""
    task_id = task["id"]
    log(f"调用 Codex runner: task_id={task_id}, timeout={TASK_TIMEOUT_SECONDS}s")
    return run_command(
        [str(CODEX_RUNNER), str(prompt_path), task_id, task["type"], str(task_path)],
        label=f"codex_runner task_id={task_id}",
        timeout=TASK_TIMEOUT_SECONDS,
    )


def mark_failed(
    task_path,
    task,
    started_at,
    started_time,
    message,
    details="",
    runner="codex",
):
    """把失败任务移动到 failed，并写入 v2 失败结果。"""
    task_id = task["id"]
    append_run_log(task_id, f"failed: {message}")
    if details.strip():
        append_run_log(task_id, details.rstrip())

    write_result_files(task, "failed", started_at, started_time, error=message, runner=runner)
    failed_path = move_task(task_path, FAILED_DIR)
    log(f"任务失败: task_id={task_id}, reason={message}")
    log(f"任务已移动到 failed: {failed_path.name}")
    return failed_path


def process_task(pending_path):
    """处理单个 pending task。"""
    log(f"发现 GitHub pending 任务文件: {pending_path.name}")

    try:
        raw_task = load_task(pending_path)
    except json.JSONDecodeError as error:
        task = normalize_task(
            {
                "id": pending_path.stem,
                "type": "analysis_task",
                "goal": "Invalid JSON task",
            },
            pending_path,
        )
        started_at = iso_now()
        message = f"JSON 解析失败: {error}"
        log(message)
        mark_failed(pending_path, task, started_at, time.time(), message)
        return True

    task = normalize_task(raw_task, pending_path)
    task_id = task["id"]

    skip_reason = should_skip_task(task, pending_path)
    if skip_reason == "archived_duplicate":
        log(f"重复任务已归档，计入本轮状态变更: {pending_path.name}")
        return True

    if skip_reason:
        return False

    started_at = iso_now()
    started_time = time.time()
    append_run_log(task_id, f"start type={task['type']} source={pending_path}")
    log(f"task开始时间: task_id={task_id}, type={task['type']}, start={started_at}")

    running_path = move_task(pending_path, RUNNING_DIR)
    log(f"任务已移动到 running: {running_path.name}")

    prompt_path = write_prompt_file(task)
    log(f"已生成 prompt: {prompt_path}")
    append_run_log(task_id, f"prompt={prompt_path}")

    runner_result = run_codex(prompt_path, task, running_path)
    runner_output = "\n".join(
        part for part in [runner_result.stdout, runner_result.stderr] if part.strip()
    )

    if runner_output.strip():
        append_run_log(task_id, runner_output.rstrip())

    if runner_result.timed_out:
        message = f"任务超时，超过 {TASK_TIMEOUT_SECONDS} 秒"
        log(f"codex输出状态: task_id={task_id}, status=failed, reason=timeout")
        mark_failed(running_path, task, started_at, started_time, message, runner_output)
        log(f"task结束时间: task_id={task_id}, end={now_text()}")
        return True

    runner_status, runner_name, runner_details = read_runner_status(task_id)
    log(
        f"codex输出状态: task_id={task_id}, "
        f"status={runner_status}, runner={runner_name}"
    )

    if runner_result.returncode != 0 or runner_status == "failed":
        message = (
            f"runner 执行失败: exit_code={runner_result.returncode}, "
            f"status={runner_status}"
        )
        mark_failed(
            running_path,
            task,
            started_at,
            started_time,
            message,
            runner_output or runner_details,
            runner=runner_name,
        )
        log(f"task结束时间: task_id={task_id}, end={now_text()}")
        return True

    if runner_status not in ["success", "fallback"]:
        message = (
            f"runner 返回未知状态: exit_code={runner_result.returncode}, "
            f"status={runner_status}"
        )
        mark_failed(
            running_path,
            task,
            started_at,
            started_time,
            message,
            runner_output or runner_details,
            runner=runner_name,
        )
        log(f"task结束时间: task_id={task_id}, end={now_text()}")
        return True

    write_result_files(task, runner_status, started_at, started_time, runner=runner_name)
    done_path = move_task(running_path, DONE_DIR)
    log(f"任务已移动到 done: {done_path.name}")
    log(f"task结束时间: task_id={task_id}, end={now_text()}")
    return True


def scan_once():
    """扫描一次 GitHub pull 下来的 pending 目录。pending 为空时不执行 Codex。"""
    task_files = sorted(PENDING_DIR.glob("*.json"))

    if not task_files:
        log("tasks/pending 为空，进入 sleep，不执行 Codex")
        return 0

    processed_task_count = 0
    for task_path in task_files:
        if process_task(task_path):
            processed_task_count += 1

    return processed_task_count


def main():
    """启动 worker，持续执行 GitHub -> 本地 -> Codex -> GitHub 闭环。"""
    ensure_directories()
    log(f"启动 GitHub 驱动 worker，项目根目录: {ROOT_DIR}")
    log(f"每 {SCAN_INTERVAL_SECONDS} 秒循环一次，任务源: {PENDING_DIR}")

    if not check_git_ready():
        log("worker 未启动。请按 README 完成 GitHub 仓库初始化后重试。")
        return

    # 启动时先拉取一次 GitHub 任务。失败后继续进入循环，但不会执行任务。
    startup_pull_ok = git_pull("startup")
    if not startup_pull_ok:
        log("启动 pull 失败，将继续等待下一轮 pull 成功")

    while True:
        processed_task_count = 0

        # 每轮循环前必须先 pull；失败时跳过执行，避免使用过期本地任务。
        pull_ok = git_pull("loop_start")
        if pull_ok:
            processed_task_count = scan_once()
            log(f"本轮处理任务数: {processed_task_count}")
        else:
            log("本轮跳过任务执行: git pull 未成功，GitHub 最新任务状态未知")

        # 只有真的处理了任务，才把结果、任务状态、日志推回 GitHub。
        sync_results_to_github(processed_task_count)
        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
