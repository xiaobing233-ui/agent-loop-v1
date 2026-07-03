# GPT + GitHub + Codex 自动任务执行系统

这是一个轻量的 GitHub 驱动 Agent 闭环系统：

GitHub Repo tasks -> git pull -> 执行任务 -> 生成结果 -> git push 回写

项目只使用 Python 标准库、bash 和 git，不依赖第三方框架。

## 项目结构

```text
agent-loop-v1/
├── tasks/
│   ├── pending/   # GitHub 任务来源
│   ├── running/   # 正在执行的任务
│   ├── done/      # 已执行成功的任务
│   └── failed/    # 执行失败的任务
├── outputs/       # 每个任务的输出结果
├── logs/
│   ├── system.log
│   └── conflict_backup/
├── worker/
│   ├── agent.py
│   ├── codex_runner.sh
│   └── init_github.sh
└── README.md
```

## 初始化 GitHub 仓库

第一步，进入项目目录：

```bash
cd agent-loop-v1
```

第二步，初始化 git repo：

```bash
git init
```

第三步，设置默认分支为 `main`：

```bash
git branch -M main
```

第四步，绑定远程仓库。请把 URL 换成你自己的 GitHub repo：

```bash
git remote add origin <YOUR_GITHUB_REPO_URL>
```

也可以使用脚本完成初始化：

```bash
chmod +x worker/init_github.sh
./worker/init_github.sh <YOUR_GITHUB_REPO_URL>
```

首次提交项目结构：

```bash
git add .
git commit -m "init agent loop"
git push -u origin main
```

## 启动 worker

启动前请确认：

```bash
git remote -v
git branch --show-current
```

必须满足：

```text
当前目录是 git repo
已设置 origin
当前分支是 main
```

启动 worker：

```bash
python3 worker/agent.py
```

worker 启动时会先执行：

```bash
git pull origin main
```

每轮循环开始前也会执行：

```bash
git pull origin main
```

每轮循环结束后会执行：

```bash
git add .
git commit -m "auto sync task results"
git push origin main
```

如果 `git pull` 或 `git push` 失败，会自动重试 3 次，并写入：

```text
logs/system.log
```

## GitHub 任务来源

任务来源严格是 GitHub 仓库里的：

```text
tasks/pending/
```

请在 GitHub 上新增 task 文件，不要把本地手动创建任务作为主流程。

示例 task：

```json
{
  "id": "task_001",
  "goal": "让 Codex 生成一个 Python 脚本，用来读取 CSV 并计算平均值",
  "input": {},
  "constraints": {
    "language": "Python",
    "dependencies": "只使用 Python 标准库"
  }
}
```

保存到 GitHub：

```text
tasks/pending/task_001.json
```

worker 每轮会先从 GitHub pull 最新任务。如果 `tasks/pending/` 为空，worker 只会 sleep，不会执行 Codex。

## 执行结果

每个任务会生成自己的输出目录：

```text
outputs/{task_id}/
```

结构化结果写入：

```text
outputs/{task_id}/result.json
```

格式如下：

```json
{
  "task_id": "task_001",
  "status": "success",
  "output_file": "outputs/task_001/output.txt",
  "log": "执行日志"
}
```

成功的 task 文件会移动到：

```text
tasks/done/
```

失败的 task 文件会移动到：

```text
tasks/failed/
```

失败时还会写入：

```text
outputs/{task_id}/error.log
```

## 冲突处理

如果 `git pull` 发生冲突，worker 会自动：

1. 备份本地冲突版本到 `logs/conflict_backup/`
2. 保留 GitHub 远端版本
3. 把处理过程写入 `logs/system.log`

这个策略让 GitHub 始终作为任务源优先。

## Codex CLI 和 fallback

`worker/codex_runner.sh` 会自动检测本机是否安装了 `codex` 命令。

如果已安装，会调用：

```bash
codex "<prompt内容>"
```

如果没有安装，会使用 Python 标准库 fallback。当前 fallback 会在任务提到 CSV 时生成一个简单的 `csv_average.py`，并把说明写入：

```text
outputs/{task_id}/output.txt
```
