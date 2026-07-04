# Frame Scoring Pipeline Prototype v0.1

## Task 015 目标

task_015 建立“视频抽帧 -> 单帧评分 -> Top N 候选帧排序”的 prototype。它服务于 Cover Decision + Generation System 的自动选帧阶段，不是单次封面设计任务。

本任务只实现脚本、prompt、文档和 dry-run 校验。不实际分析视频，不读取 task_013 的原始图片样本，不调用视觉 API，不在 Codex 窗口里调用 Codex CLI。

## 与 task_013 / task_014 的关系

- task_013 提供 Cover Reverse Dataset V2，包含 19 张历史封面的反推结构。
- task_014 基于 task_013 生成 Frame Scoring v0.1 权重体系。
- task_015 将 task_014 的权重体系接入到视频帧候选排序流程。

## 视频抽帧流程

脚本：`scripts/task015_extract_frames.py`

输入一个视频路径，使用 `ffmpeg` 按固定间隔抽帧：

```bash
python scripts/task015_extract_frames.py --video "/path/to/video.mp4" --interval-sec 2 --max-frames 80
```

输出：

- `outputs/task_015/frames/frame_0001.jpg`
- `outputs/task_015/frame_manifest.json`

`frame_manifest.json` 记录 `frame_id`、`video_path`、`frame_path`、`timestamp_sec`、`width`、`height` 和 `extraction_version`。

如果 `ffmpeg` 不存在，脚本会明确报错。抽出的帧属于 runtime 产物，不提交到 Git。

### ffmpeg 依赖解析

抽帧脚本支持三种 ffmpeg 来源，按以下优先级解析：

1. 环境变量 `TASK015_FFMPEG_BIN`
2. PATH 里的系统 `ffmpeg`
3. Python 包 `imageio-ffmpeg` 的 fallback：`imageio_ffmpeg.get_ffmpeg_exe()`

可以用轻量检查命令确认当前会使用哪个 ffmpeg，不读取视频也不生成帧：

```bash
python3 scripts/task015_extract_frames.py --check-ffmpeg
```

如果三种方式都不可用，脚本会报错：`ffmpeg not found; install ffmpeg or pip install imageio-ffmpeg`。

## 单帧评分流程

脚本：`scripts/task015_score_frame.py`

输入：

- `outputs/task_015/frame_manifest.json`
- `outputs/task_014/frame_scoring_weights.json`
- `prompts/task015_single_frame_scoring_prompt.md`

示例：

```bash
python scripts/task015_score_frame.py --frame-id frame_0001 --backend codex_cli
python scripts/task015_score_frame.py --index 1 --dry-run
```

默认 backend 为 `codex_cli`。`--dry-run` 只生成 runtime prompt，不调用 Codex CLI。

Codex CLI 可执行文件优先级：

1. `TASK015_CODEX_BIN`
2. PATH 里的 `codex`
3. `/Applications/Codex.app/Contents/Resources/codex`

Codex CLI 命令形态：

```bash
<codex_bin> -a never exec --skip-git-repo-check -C <repo> -o <raw_output_path> -
```

输出：

- runtime prompt: `outputs/task_015/runtime_prompts/frame_0001.md`
- raw output: `outputs/task_015/codex_raw/frame_0001.txt`
- frame score: `outputs/task_015/frame_scores/frame_0001.json`

如果 raw 输出不是合法 JSON，脚本会依次尝试直接 `json.loads`、提取 markdown JSON 代码块、提取第一个完整 JSON object。仍失败则写 `status=failed`。脚本不会从“完成 · success”这类自然语言输出中编造评分。

## Top N 排序逻辑

脚本：`scripts/task015_rank_frames.py`

```bash
python scripts/task015_rank_frames.py --top-n 10
```

流程：

1. 读取 `outputs/task_015/frame_scores/*.json`
2. 只纳入 `status=success` 的帧
3. 按 `final_score` 降序排序
4. 输出 `outputs/task_015/ranked_frames.json`
5. 输出 `outputs/task_015/top_candidates.md`

`top_candidates.md` 包含 Top N、时间戳、分数、decision band、推荐原因、风险提示和后续生成封面 prompt 可用信号。

## 为什么 Codex CLI 评分必须在 Mac 终端执行

当前 Codex 窗口内不应二次调用 Codex CLI。之前诊断显示，沙箱环境里可能出现本地状态库只读或 app-server 初始化失败。Mac 终端可以按系统权限直接运行 Codex CLI，因此真实视觉评分步骤应由用户在 Mac 终端执行。

本仓库脚本保留 `codex_cli` backend，是为了让终端流程可复用，而不是让 Codex 窗口递归调用自己。

## Git 提交边界

可以提交：

- `scripts/task015_extract_frames.py`
- `scripts/task015_score_frame.py`
- `scripts/task015_rank_frames.py`
- `prompts/task015_single_frame_scoring_prompt.md`
- `docs/frame_scoring_pipeline_v0_1.md`
- `outputs/task_015/result.json`
- `outputs/task_015/result.md`
- `.gitignore`

不提交：

- `outputs/task_015/frames/`
- `outputs/task_015/runtime_prompts/`
- `outputs/task_015/runtime_images/`
- `outputs/task_015/codex_raw/`
- `outputs/task_015/frame_scores/`

当前建议是不默认提交真实视频跑出来的 `frame_scores`。原因是它们绑定具体视频素材和运行时视觉分析结果，后续可以在需要复现实验时单独提交经过筛选的 benchmark，而不是把每次 runtime 结果都纳入版本库。

## 后续 task_016 如何接 Top 3 封面生成

task_016 可以读取 `ranked_frames.json` 的 Top 3 或 Top N 结果，为每个候选帧生成封面布局方案：

1. 根据 `generation_prompt_signals` 生成 image2 prompt 初稿。
2. 根据 `title_space_assessment` 决定标题区域和版式。
3. 根据 `visual_risk_notes` 与 penalties 设置负向约束。
4. 对 Top 3 生成封面候选图。
5. 使用 QA 层检查中文标题、品牌元素、主体完整性、AI 瑕疵和平台适配。
