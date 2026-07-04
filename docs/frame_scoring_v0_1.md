# Frame Scoring v0.1

## 背景

Frame Scoring v0.1 是 Cover Decision + Generation System 的视频自动选帧评分方案。它不是单次封面设计稿，而是给后续流程使用的候选帧排序规则：从视频帧中优先挑出适合承载标题、产品/教育信息、品牌场景和后续图生图生成的画面。

## 输入数据来源

- `outputs/task_013/dataset.json`
- `outputs/task_013/pattern_summary.md`
- `outputs/task_013/per_cover/*.json`
- `docs/cover_reverse_table_v2.md`

本次没有读取原始图片，没有调用视觉 API，没有调用 Codex CLI，也没有生成图片。

## N=19 数据说明

task_013 数据集中共有 19 条单图分析记录：

| Label | Count |
| --- | ---: |
| satisfied | 16 |
| unsatisfied | 3 |
| unknown | 0 |

所有 19 条记录为 `status=success`。但数据也有明显限制：Decision 层的 `scene_classification`、`frame_type`、`layout_type`、`click_logic`、`reusable_pattern` 多数为空，数值信号字段基本为 0；QA 层多数字段也较稀疏。因此 v0.1 的高置信依据主要来自 `reusable_prompt_signals`、`negative_constraints`、`risk_notes` 和 `pattern_summary.md`，而不是统计显著的数值回归。

## Satisfied / Unsatisfied 差异

### 高置信结论

- 满意样本反复出现大字号中文标题、高对比白字、左侧标题区、品牌角标、科技教育背景、产品/设备/活动语境等可复用信号。
- 负向约束集中在标题可读性、低对比背景、复杂背景、过多小字、人物或产品遮挡标题、中文文字失真、品牌/活动/肖像授权风险。
- pattern_summary 明确提出低分或不满意样本应优先检查标题可读性、主体清晰度、构图重心和生成瑕疵风险。

### v0.1 假设

- 情绪张力、事件感、人物表情、人脸信号对点击有影响，但 task_013 的对应数值字段为空或为 0，不能直接估计权重。
- unsatisfied 只有 3 条，差异结论更适合作为初始规则，而不是稳定统计结论。
- QA 层字段稀疏，常见风险主要从 `risk_notes` 与 `negative_constraints` 推导。

## Frame Scoring v0.1 总表

正向维度总权重为 100。每个维度按 0-5 分打分，正向得分计算为 `weight * score / 5`。

| ID | Dimension | Weight |
| --- | --- | ---: |
| D01 | 主体清晰度 | 14 |
| D02 | 标题承载空间与可读性 | 15 |
| D03 | 画面层次与视觉重心 | 12 |
| D04 | 教育/产品信息可读性 | 11 |
| D05 | 点击欲望与情绪/冲突张力 | 10 |
| D06 | 品牌/直播场景匹配度 | 9 |
| D07 | 信息密度控制 | 9 |
| D08 | AI 生成可控性 | 8 |
| D09 | 后期排版成本 | 7 |
| D10 | 复用安全性与授权风险 | 5 |
| **Total** |  | **100** |

## 每个维度的评分定义

### D01 主体清晰度

- Weight: 14
- High score: 主体一眼可辨，人物、产品、证书、活动屏幕或关键物件没有被遮挡、裁切或背景吞没。
- Low score: 主体过小、边缘裁切、被文字或装饰遮挡，或多主体抢焦导致无法判断封面核心。
- Evidence: task_013 的复用信号包含 presenter、product/device、conference banner、certificate、mascot 等主体线索；risk_notes 多次提醒人物、设备、证书和品牌元素的遮挡、误复刻或授权风险。
- Auto-frame note: 优先检测主体面积、完整度和主体-背景边界清晰度。

### D02 标题承载空间与可读性

- Weight: 15
- High score: 画面有稳定的大标题区域，背景对比足够，主体不会压住主标题。
- Low score: 标题区被人物、产品、复杂背景或强透视占用；主标题容易过小、低对比或被装饰抢占。
- Evidence: pattern_summary 的负向约束高频项包括低对比浅色背景、过多小字、星芒抢标题、标题字号弱化；满意样本复用信号出现 large bold Chinese headline、high contrast white typography。
- Auto-frame note: 选帧时估计可排版空区和标题落点对比度，没有标题空间的帧不应进入 top candidate。

### D03 画面层次与视觉重心

- Weight: 12
- High score: 主体、标题、品牌/辅助信息有清晰主次，视觉动线稳定。
- Low score: 人物、标题、logo、活动元素或装饰互相抢焦，视觉重心散乱。
- Evidence: pattern_summary 把构图重心列为低分/不满意样本优先检查项；risk_notes 提到复杂拼贴、小字和强透视会降低缩略图可读性。
- Auto-frame note: 用主体面积、留白比例、边缘复杂度和高对比区域数量估算层次。

### D04 教育/产品信息可读性

- Weight: 11
- High score: 教育主题、AI/产品功能、活动或荣誉信息能被快速识别，且不依赖大量小字。
- Low score: 主题需要读很多小字才明白，产品或活动标识不可辨认。
- Evidence: reusable_prompt_signals 高频出现 AI education、科技教育背景、产品设备、功能标签、会议/活动标识；risk_notes 提醒功能承诺和品牌/活动文字需要校对。
- Auto-frame note: 对课程、产品、直播、活动帧分别检测是否有明确内容物。

### D05 点击欲望与情绪/冲突张力

- Weight: 10
- High score: 画面和标题空间能形成问题、结果、反差、事件感或强利益点。
- Low score: 画面只是普通说明性截图，没有继续点击的理由。
- Evidence: task_013 样本包含 answer-revealing headline tone、AI+教育落地、活动唯一性、功能演示等信号；但 emotion_signal/event_signal 数值不可用。
- Auto-frame note: 优先选择有手势、指向、奖项、产品能力展示、场景事件或可承接问题标题的帧。

### D06 品牌/直播场景匹配度

- Weight: 9
- High score: 画面适合视频号/直播封面语境，品牌角标、活动场景、课程/产品气质一致。
- Low score: 舞台、展会、证书、产品或人物风格与直播封面目标冲突。
- Evidence: 满意样本多次出现 top-left brand logo、科技教育背景、产品/会议视觉；unsatisfied risk_notes 提到正式企业荣誉与深紫蓝霓虹舞台风格存在质感冲突。
- Auto-frame note: 按视频类型设置风格匹配阈值，不同业务场景不能共用单一美术标准。

### D07 信息密度控制

- Weight: 9
- High score: 主信息集中，辅助信息少而清楚，背景和装饰不会增加阅读负担。
- Low score: 多层小字、多个标签、复杂背景、拼贴照片和装饰同时出现。
- Evidence: negative_constraints 包含不要过多小字、不要复杂背景、不要暗色脏污质感；risk_notes 多次提到小屏展示、小字和复杂拼贴风险。
- Auto-frame note: 用小目标数量、文字区域数量和背景纹理复杂度做自动惩罚。

### D08 AI 生成可控性

- Weight: 8
- High score: 主体、背景、标题区和品牌元素可被清楚描述，生成时可控，中文文字可后期排版。
- Low score: 依赖复杂手部、真实品牌细节、小字证书、真人肖像或密集拼贴。
- Evidence: risk_notes 高频出现中文文字失真、品牌/活动标识授权、手部畸形、产品透视漂浮、证书小字风险。
- Auto-frame note: 优先选择可拆成主体、背景、标题区的帧；高风险帧进入人工或后期排版链路。

### D09 后期排版成本

- Weight: 7
- High score: 后期只需放置主标题和少量角标即可完成。
- Low score: 需要大面积擦除背景、重做标题区、抠人物/产品、修复小字或调整多个品牌元素。
- Evidence: task_013 多处建议中文标题需后期真实排版，产品叠图、品牌标识和小字都需要单独控制。
- Auto-frame note: 低返工帧优先推给自动生成链路，高返工帧仅保留为参考。

### D10 复用安全性与授权风险

- Weight: 5
- High score: 画面可泛化为通用场景，不依赖真实人物身份、未授权品牌、真实活动标识或不可验证强主张。
- Low score: 高度依赖可识别人物、品牌 logo、活动名、证书小字、肖像或商标。
- Evidence: satisfied 与 unsatisfied 样本均有 risk_notes 提到不要识别人物身份、品牌/大会/肖像/商标授权、强主张事实核验。
- Auto-frame note: 低安全性不一定立即淘汰，但必须影响后续生成策略和审核优先级。

## 权重设计理由

标题承载空间与主体清晰度权重最高，因为 task_013 的负向约束和总结均反复指向标题可读性、主体清晰度和构图重心。教育/产品信息、点击钩子和品牌/直播匹配是中高权重，因为它们决定封面是否能服务视频号业务目标。AI 生成可控性、后期排版成本和复用安全性权重较低但不可删除，因为它们决定系统是否能稳定自动化，而不是只选出视觉上好看的帧。

## Penalty 规则

penalty 不计入 100 分正向权重，而是在正向分之后扣减。v0.1 建议总扣分最多封顶为 -25，除非触发硬拒绝。

| Penalty | Points | Trigger |
| --- | ---: | --- |
| 文字不可读或小字过多 | -12 | 主标题或关键信息在缩略图尺寸下不可读。 |
| 无稳定标题区 | -10 | 主体或复杂背景占满画面，无法放置高对比标题。 |
| 标题背景低对比 | -8 | 标题预计落点背景过亮、过花或与文字颜色接近。 |
| 杂乱或抢焦 | -8 | 装饰、logo、拼贴、人物、产品和标题互相抢焦。 |
| AI 生成瑕疵高风险 | -7 | 依赖复杂手部、证书小字、真实 logo、中文长文或产品透视。 |
| 平台/业务风格不匹配 | -7 | 风格与视频号直播、教育产品或正式活动封面目标明显不一致。 |
| 授权或人物身份风险 | -6 | 可识别人物身份、真实品牌/活动/证书信息且后续复用不可控。 |

## 后续如何用于视频自动选帧

1. 从视频中抽取候选帧，过滤模糊、黑屏、运动拖影和无主体帧。
2. 对每个候选帧打 10 个正向维度分。
3. 按 penalty 规则扣分，得到 `final_score`。
4. 按阈值分层：
   - below 55: reject
   - 55-64: weak candidate
   - 65-74: acceptable candidate
   - 75-84: strong candidate
   - 85-100: top candidate
5. 对 top/strong candidate 生成后续布局建议和 image2 prompt 初稿。
6. 高风险但高分帧进入人工审核或分层生成：主体/背景使用图像生成，中文标题和品牌元素由后期排版完成。

## v0.2 需要补充的数据

- 更多不满意样本，至少把 unsatisfied 扩展到 20 条以上。
- 每张封面的真实 CTR、播放率、完播率、转化率或人工点击偏好分。
- 视频源帧级数据：同一视频的多个候选帧和最终选中封面对比。
- 完整 Decision 数值字段：主体清晰度、标题空间、构图、信息密度、情绪/事件信号。
- QA 层真实通过/失败原因，而不是仅靠 risk_notes 推断。
- 不同业务场景的独立权重：教育直播、产品发布、活动荣誉、课程转化。
