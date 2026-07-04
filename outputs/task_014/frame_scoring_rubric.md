# Frame Scoring v0.1 Rubric

Use this rubric for both human review and model-assisted frame scoring. Score each dimension from 0 to 5, then apply penalties from `frame_scoring_weights.json`.

## General Scale

| Score | Meaning |
| --- | --- |
| 0 | Unusable for an automatic cover candidate. |
| 1 | Weak; possible only with heavy manual repair. |
| 3 | Usable but has clear tradeoffs or requires some post work. |
| 5 | Strong candidate; clear, readable, and easy to turn into a cover. |

## Dimension Rubric

| Dimension | 0 | 1 | 3 | 5 |
| --- | --- | --- | --- | --- |
| D01 主体清晰度 | No clear subject. | Subject exists but is tiny, cropped, or buried. | Main subject is usable but has some obstruction or weak boundaries. | Main subject is immediately clear and complete. |
| D02 标题承载空间与可读性 | No place for title. | Title could fit only after heavy masking or cropping. | There is a workable title area with some contrast risk. | Large high-contrast title area is obvious. |
| D03 画面层次与视觉重心 | No visual hierarchy. | Too many competing focal points. | Hierarchy is acceptable but not clean. | Strong subject-title-brand order. |
| D04 教育/产品信息可读性 | Theme cannot be inferred. | Theme relies on small text or ambiguous props. | Education/product/event cue is visible but not dominant. | Topic and business value are immediately legible. |
| D05 点击欲望与情绪/冲突张力 | No hook. | Generic frame with little reason to click. | Some event, result, question, or benefit signal. | Strong curiosity, result promise, contrast, or event energy. |
| D06 品牌/直播场景匹配度 | Clearly wrong for the platform or business. | Style feels off or brand placement is awkward. | Usable with minor brand/layout adjustment. | Fits video account, live cover, and brand tone naturally. |
| D07 信息密度控制 | Overloaded and unreadable. | Too much clutter or too many small elements. | Manageable density with some cleanup needed. | Clean main message with limited supporting elements. |
| D08 AI 生成可控性 | Very likely to generate artifacts or unusable text. | Many risky details, small logos, hands, or dense text. | Some risky elements but can be constrained. | Easy to describe, regenerate, and QA. |
| D09 后期排版成本 | Requires full redesign. | Heavy masking, retouching, or text rebuilding. | Moderate post work. | Minimal layout work after frame selection. |
| D10 复用安全性与授权风险 | High identity, trademark, or factual claim risk. | Several reuse risks need review. | Manageable risk with replacement guidance. | Safe to generalize as a reusable pattern. |

## Common Deductions

- Deduct heavily when the title would be unreadable on mobile.
- Deduct when the subject is clear but leaves no title space.
- Deduct when logo, certificate, activity name, or small text must be replicated exactly.
- Deduct when the scene is attractive but does not support the video account or live-cover purpose.
- Deduct when a frame would require too much manual repair before image generation.

## Special Cases

### Insufficient Visual Information

If the frame does not provide enough visible subject, scene, or topic information, score most dimensions at 0 or 1. Do not infer missing business context from the video title alone.

### Clear Person But No Title Space

Give subject clarity a fair score, but reduce title space, visual hierarchy, information density control, and post-layout cost. A clear face alone is not enough for this cover system.

### Beautiful Frame But Poor Live-Cover Fit

Score visual hierarchy or aesthetics normally, but lower platform/brand fit and click hook if the frame feels like a generic photo, cinematic still, or event snapshot rather than a video account cover.

### High AI Generation Risk

If the frame relies on readable Chinese text, certificate details, true logos, hands, or precise product geometry, reduce AI generation controllability and apply the artifact-risk penalty. Prefer using the frame as a reference while recreating text and brand elements in controlled layout layers.

### Risk Notes

Risk penalties do not replace positive scoring. A frame may score high and still require review if it contains identity, trademark, factual claim, or generation-control risk.
