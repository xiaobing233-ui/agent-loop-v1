# GPT + GitHub + Codex 自动任务执行系统 v2

这是一个轻量的 GitHub 驱动 Agent 闭环系统：

GitHub Repo tasks -> git pull -> 执行任务 -> 生成结果 -> git push 回写

项目只使用 Python 标准库、bash 和 git，不依赖第三方框架。

## 项目结构

```text
agent-loop-v1/
├── schema/
│   └── task_schema_v2.json
├── templates/
│   ├── code_task.json
│   ├── analysis_task.json
│   └── design_prompt_task.json
├── tasks/
│   ├── pending/   # GitHub 任务来源
│   ├── running/   # 正在执行的任务
│   ├── done/      # 已执行成功的任务
│   └── failed/    # 执行失败的任务
├── outputs/       # 每个任务的标准输出
├── logs/
│   ├── system.log
│   └── conflict_backup/
└── worker/
    ├── agent.py
    ├── codex_runner.sh
    └── init_github.sh
```

## 初始化 GitHub 仓库

```bash
cd agent-loop-v1
git init
git branch -M main
git remote add origin <YOUR_GITHUB_REPO_URL>
git add .
git commit -m "init agent loop"
git push -u origin main
```

也可以使用脚本：

```bash
chmod +x worker/init_github.sh
./worker/init_github.sh <YOUR_GITHUB_REPO_URL>
```

## 启动 worker

启动前确认当前目录是 git repo、已经设置 `origin`、当前分支是 `main`：

```bash
git remote -v
git branch --show-current
```

启动：

```bash
python3 worker/agent.py
```

worker 会持续执行：

```text
git pull origin main
扫描 tasks/pending/
执行任务
写入 outputs/{task_id}/
git add .
git commit -m "auto sync task results"
git push origin main
```

如果 `git pull` 或 `git push` 失败，会自动重试 3 次，并写入 `logs/system.log`。

## v2 任务格式

标准 schema 在：

```text
schema/task_schema_v2.json
```

v2 task 示例：

```json
{
  "id": "task_002",
  "type": "analysis_task",
  "goal": "任务目标",
  "input": {
    "files": [],
    "text": ""
  },
  "constraints": {
    "language": "zh-CN",
    "output_format": "markdown + json",
    "dependencies": "只使用必要依赖"
  },
  "expected_outputs": [
    "outputs/task_002/result.md",
    "outputs/task_002/result.json"
  ],
  "status": "pending"
}
```

支持的 `type`：

```text
code_task
analysis_task
file_task
design_prompt_task
```

worker 仍然兼容旧版 task。旧版缺少的 `type`、`input.files`、`input.text`、`expected_outputs` 会自动补默认值。

## 如何创建新任务

推荐从 `templates/` 复制一个模板：

```text
templates/code_task.json
templates/analysis_task.json
templates/design_prompt_task.json
```

在 GitHub 网页中进入：

```text
tasks/pending/
```

新建文件，例如：

```text
task_002.json
```

把模板内容复制进去，修改 `id`、`type`、`goal`、`input.text`，然后 commit 到 `main` 分支。

worker 下一轮会自动 pull 并执行。

## 标准输出

每个任务都会生成：

```text
outputs/{task_id}/result.json
outputs/{task_id}/result.md
outputs/{task_id}/run.log
```

`result.json` 标准格式：

```json
{
  "task_id": "task_002",
  "type": "analysis_task",
  "status": "success",
  "runner": "codex",
  "started_at": "2026-07-03T15:00:00",
  "finished_at": "2026-07-03T15:00:01",
  "duration_seconds": 1.0,
  "summary": "任务摘要",
  "output_files": [],
  "error": ""
}
```

`result.md` 给人阅读。  
`run.log` 记录执行过程。

## 如何判断任务成功

`result.json` 里的 `status` 有 3 种重要语义：

```text
success  = 真正执行器成功完成，runner 通常是 codex
fallback = 系统流程成功，但没有真正调用 Codex，只生成兜底摘要
failed   = 执行失败
```

只有满足下面 3 个条件，才算真正业务成功：

```text
tasks/done/{task_id}.json 存在
outputs/{task_id}/result.json 存在
result.json 里的 status 是 success
```

如果 `status` 是 `fallback`，说明 worker 闭环跑通了，但没有真正调用 Codex。需要检查本地是否安装 `codex` CLI，以及运行 worker 的终端里 `codex` 命令是否可用。

worker 还会防止重复执行：

```text
tasks/done/ 已有同名任务文件 -> 不再执行
outputs/{task_id}/result.json 已是 success -> 不再执行
tasks/running/ 已有同名任务文件 -> 不重复启动
```

## 如何查看失败原因

如果任务失败，会移动到：

```text
tasks/failed/
```

查看这些文件：

```text
outputs/{task_id}/result.json
outputs/{task_id}/result.md
outputs/{task_id}/run.log
logs/system.log
```

`result.json` 中：

```json
{
  "status": "failed",
  "error": "失败原因"
}
```

## 后续如何让 GPT 生成 task.json

可以把下面这段提示词给 GPT：

```text
请按照 schema/task_schema_v2.json 生成一个任务 JSON。
要求：
1. id 使用 task_数字
2. type 只能是 code_task、analysis_task、file_task、design_prompt_task
3. status 必须是 pending
4. expected_outputs 必须包含 outputs/{id}/result.md 和 outputs/{id}/result.json
5. 只输出 JSON，不要输出解释
```

把 GPT 生成的 JSON 保存到 GitHub：

```text
tasks/pending/{task_id}.json
```

worker 会自动完成后续闭环。

## Codex CLI 和 fallback

`worker/codex_runner.sh` 会自动检测本机是否安装了 `codex` 命令。

如果已安装，会调用：

```bash
codex "<prompt内容>"
```

如果没有安装，会使用 Python 标准库 fallback。fallback 会写入 `output.txt`、`result.md`、`result.json` 和 `run.log`，但 `result.json` 会明确标记：

```json
{
  "status": "fallback",
  "runner": "python_fallback"
}
```

看到 `fallback` 时，不要把它当作真正的业务结果；请先确认 `command -v codex` 能在启动 worker 的同一个终端里找到 Codex CLI。
