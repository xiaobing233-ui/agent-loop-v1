You are scoring exactly one extracted video frame for Cover Decision + Generation System.

Read the Frame Scoring v0.1 weights provided in the prompt. Analyze only the current frame file path. Do not compare with other frames unless their data is explicitly provided. Do not generate images. Do not output Markdown. Do not output code fences. Do not output "完成", "success", or any natural-language summary outside JSON.

Return exactly one JSON object that can be parsed by `json.loads`.

The JSON object must contain:

{
  "frame_id": "",
  "frame_path": "",
  "timestamp_sec": 0,
  "status": "success | failed",
  "analysis_version": "task015_frame_scoring_v0.1",
  "dimension_scores": [
    {
      "dimension_id": "",
      "score": 0,
      "rationale": ""
    }
  ],
  "penalties": [
    {
      "penalty_id": "",
      "points": 0,
      "reason": ""
    }
  ],
  "weighted_score": 0,
  "penalty_score": 0,
  "final_score": 0,
  "decision_band": "",
  "recommendation": "",
  "title_space_assessment": "",
  "subject_assessment": "",
  "visual_risk_notes": [],
  "generation_prompt_signals": [],
  "error_summary": ""
}

If you cannot perform real visual analysis of the frame, return valid JSON with status="failed", empty score arrays, final_score=0, and a short error_summary. Do not invent visual observations.
