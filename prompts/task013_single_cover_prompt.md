Analyze only the current single cover image.

Do not reference, compare, or infer from any other cover. Do not generate images. Do not identify or evaluate a person's identity. Evaluate only visible design, composition, text hook, emotional signal, product/event/UI cues, and likely click logic.

Output strict JSON only. Do not output explanations. Do not output Markdown. Use the unified scoring schema exactly:

{
  "cover_id": "",
  "source_file": "",
  "file_name": "",
  "label": "satisfied | unsatisfied | unknown",
  "analysis_status": "success | needs_model_analysis | failed",
  "scene_classification": "Education | Event | Human | Product",
  "frame_type": "face_dominant | product_dominant | ui_dominant | mixed",
  "face_signal": 0.0,
  "emotion_signal": 0.0,
  "composition_signal": 0.0,
  "information_density": 0.0,
  "event_signal": 0.0,
  "title_hook_type": [],
  "layout_type": "hero_face | product_showcase | ui_overlay | split_narrative",
  "click_logic": "",
  "performance_label": "high | medium | low",
  "reusable_pattern": "",
  "scoring_notes": ""
}
