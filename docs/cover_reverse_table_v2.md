# 20封面反推分析表 V2：Decision + Generation 双层结构

## 表结构四层

| 层级 | 名称 | 作用 |
| --- | --- | --- |
| 1 | Meta 基础信息层 | 记录封面样本的基础归档信息、发布环境、表现结果和业务目标。 |
| 2 | Decision 决策层 | 反推封面为什么这样设计，提炼点击判断、构图选择和可复用决策模式。 |
| 3 | Generation 生成层 | 描述封面后续如何生成或复刻，沉淀图像生成方向、约束和风险。 |
| 4 | QA 质检层 | 建立封面可用性检查标准，用于评估生成结果是否满足投放和点击要求。 |

## Meta 基础信息层

| 字段 | 说明 |
| --- | --- |
| `cover_id` | 封面样本唯一编号。 |
| `image_file` | 对应封面图片文件。 |
| `video_type` | 视频内容类型。 |
| `publish_channel` | 发布渠道或平台。 |
| `performance_label` | 表现标签，例如高点击、低点击、待观察等。 |
| `performance_metric` | 具体表现指标，例如点击率、播放量、转化率等。 |
| `business_goal` | 该封面服务的业务目标。 |

## Decision 决策层

| 字段 | 说明 |
| --- | --- |
| `scene_classification` | 封面场景分类。 |
| `frame_type` | 画面帧类型。 |
| `face_signal` | 人脸信号及其点击影响。 |
| `emotion_signal` | 情绪信号及其强度。 |
| `composition_signal` | 构图信号，例如主体位置、视觉重心、空间关系等。 |
| `information_density` | 信息密度判断。 |
| `event_signal` | 事件感或情节触发信号。 |
| `product_visibility` | 产品可见度与识别程度。 |
| `title_hook_type` | 标题钩子类型。 |
| `layout_type` | 图文布局类型。 |
| `click_logic` | 封面驱动点击的核心逻辑。 |
| `reusable_pattern` | 可复用的封面决策模式。 |

## Generation 生成层

| 字段 | 说明 |
| --- | --- |
| `generation_mode` | 生成模式，例如参考图生成、局部重绘、纯文本生成等。 |
| `reference_frame_usage` | 参考帧使用方式。 |
| `subject_preservation` | 主体保留策略。 |
| `background_strategy` | 背景处理或替换策略。 |
| `title_area_planning` | 标题区域规划方式。 |
| `brand_element_strategy` | 品牌元素使用策略。 |
| `image2_prompt_direction` | 图生图提示词方向。 |
| `negative_constraints` | 需要避免的负向约束。 |
| `generation_risk` | 生成过程中的主要风险。 |

## QA 质检层

| 字段 | 说明 |
| --- | --- |
| `face_quality_check` | 人脸质量检查。 |
| `product_accuracy_check` | 产品准确性检查。 |
| `text_area_check` | 文案和标题区域检查。 |
| `brand_consistency_check` | 品牌一致性检查。 |
| `clickability_check` | 点击吸引力检查。 |
| `platform_fit_check` | 平台适配检查。 |
| `ai_artifact_risk` | AI 生成瑕疵风险检查。 |
| `final_usability` | 最终可用性判断。 |
| `revision_instruction` | 修改指令或返工建议。 |

这张表的目的不是做单次封面执行建议，而是用于反推封面决策逻辑、生成策略和自动质检规则，为后续 Cover Decision + Generation System 提供训练样本结构。
