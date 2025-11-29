"""MCQ generation helpers supporting both Gemini and OpenAI (ChatGPT)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from google import genai
from openai import OpenAI


_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.0-flash")


@dataclass
class GeminiResult:
    success: bool
    message: str
    payload: Dict[str, Any] | None = None


def _get_gemini_client() -> genai.Client:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set. Please update the .env file.")
    return genai.Client(api_key=api_key)


def _get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Please update the .env file.")
    return OpenAI(api_key=api_key)


def _extract_json_from_response(response: Any, provider: str) -> Dict[str, Any]:
    """Universal JSON extractor for both Gemini and OpenAI responses."""
    if provider == "gemini":
        # Gemini format: response.text or response.output_text
        raw_text = response.text if hasattr(response, "text") else response.output_text
    else:  # openai
        # OpenAI format: response.choices[0].message.content
        raw_text = response.choices[0].message.content or ""
    
    raw_text = raw_text.strip()
    # Strip code fences if wrapped
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        # remove optional language hint
        if raw_text.startswith("json"):
            raw_text = raw_text[4:].strip()
    return json.loads(raw_text)


def _build_mcq_prompt(article_title: str, article_text: str) -> str:
    return f"""
You are a medical MCQ author. Using the article below, produce:
1. A single multiple-choice question (5 options, exactly one correct).
2. At least one SNOMED-style relation triplet describing the knowledge assessed.
3. An optimized visual prompt describing an illustration that matches the scenario.

Return STRICT JSON with this schema:
{{
  "mcq": {{
    "stem": "...",
    "question": "...",
    "options": ["A", "B", "C", "D", "E"],
    "correct_option": 0   // index 0-4
  }},
  "triplets": [
    {{
      "subject": "...",
      "action": "...",
      "object": "...",
      "relation": "SNOMED-like verb"
    }}
  ],
  "visual_prompt": "text describing the desired medical illustration"
}}

Rules:
- Options must be medically plausible.
- Triplets must reflect TRUE statements from the article (at least one triplet).
- visual_prompt should be concise (<= 80 words).
- DO NOT add commentary outside the JSON.

Article title: {article_title}

Article content:
\"\"\"{article_text[:8000]}\"\"\"  // truncated if extremely long
""".strip()


def generate_mcq_with_triplets(article: Dict[str, Any], model_id: Optional[str] = None) -> GeminiResult:
    """Generate MCQ + triplets + visual prompt for the provided article.
    
    Args:
        article: Article data with title and content
        model_id: Optional model identifier. If contains "chatgpt" or "openai", uses OpenAI API.
                  Otherwise uses Gemini (default).
    """
    try:
        prompt = _build_mcq_prompt(article.get("title") or article.get("source_id", "Article"), article.get("content", ""))
        
        # Route to OpenAI if ChatGPT selected, otherwise use Gemini
        if model_id and ("chatgpt" in model_id.lower() or "openai" in model_id.lower()):
            # OpenAI API with JSON mode
            client = _get_openai_client()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a medical MCQ author. Return only valid JSON, no commentary."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            payload = _extract_json_from_response(response, "openai")
            return GeminiResult(True, "MCQ generated (ChatGPT)", payload)
        else:
            # Gemini API (default)
            client = _get_gemini_client()
            response = client.models.generate_content(
                model=_GEMINI_MODEL,
                contents=[
                    {
                        "role": "user",
                        "parts": [{"text": prompt}],
                    }
                ],
            )
            payload = _extract_json_from_response(response, "gemini")
            return GeminiResult(True, "MCQ generated (Gemini)", payload)
    except Exception as exc:  # pragma: no cover - logging handled upstream
        provider = "ChatGPT" if (model_id and ("chatgpt" in model_id.lower() or "openai" in model_id.lower())) else "Gemini"
        return GeminiResult(False, f"{provider} MCQ generation failed: {exc}", None)


def _build_critique_prompt(mcq_json: Dict[str, Any], user_feedback: str) -> str:
    """Build prompt for LoopAgent (Gemini) to critique MCQ."""
    return f"""
You are a medical MCQ critic. Review the MCQ and user feedback.

Current MCQ:
{json.dumps(mcq_json, indent=2, ensure_ascii=False)}

User Feedback:
{user_feedback}

Provide specific, actionable critique:
- What's good about the MCQ?
- What needs improvement?
- Are options medically plausible?
- Is the question clear and unambiguous?
- Does it align with the user's feedback?

Return ONLY your critique as plain text (no JSON, no code blocks, no markdown formatting).
""".strip()


def _get_critique_from_loopagent(mcq_json: Dict[str, Any], user_feedback: str) -> str:
    """Get critique from LoopAgent (Gemini) for MCQ refinement.
    
    Args:
        mcq_json: Current MCQ JSON payload
        user_feedback: User feedback text
        
    Returns:
        Critique text from Gemini
        
    Raises:
        Exception: If Gemini API call fails
    """
    client = _get_gemini_client()
    prompt = _build_critique_prompt(mcq_json, user_feedback)
    
    response = client.models.generate_content(
        model=_GEMINI_MODEL,
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
    )
    
    # Extract text from response
    raw_text = response.text if hasattr(response, "text") else response.output_text
    raw_text = raw_text.strip()
    
    # Clean up if wrapped in code fences or markdown
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("text") or raw_text.startswith("markdown"):
            raw_text = raw_text.split("\n", 1)[-1].strip()
    if raw_text.startswith("#"):
        # Remove markdown headers if present
        lines = raw_text.split("\n")
        raw_text = "\n".join(line for line in lines if not line.strip().startswith("#"))
    
    return raw_text.strip()


def _build_refinement_prompt(critique: str, mcq_json: Dict[str, Any], article: Dict[str, Any]) -> str:
    """Build prompt for Primary LLM to improve MCQ based on critique."""
    return f"""
The critic provided feedback. Improve the MCQ based on the critique.

Critique:
{critique}

Current MCQ JSON:
{json.dumps(mcq_json, indent=2, ensure_ascii=False)}

Article context:
Title: {article.get("title", "Unknown")}
Content:
\"\"\"{article.get("content", "")[:6000]}\"\"\"

Return updated JSON with the same schema:
{{
  "mcq": {{
    "stem": "...",
    "question": "...",
    "options": ["A", "B", "C", "D", "E"],
    "correct_option": 0
  }},
  "triplets": [
    {{
      "subject": "...",
      "action": "...",
      "object": "...",
      "relation": "SNOMED-like verb"
    }}
  ],
  "visual_prompt": "text describing the desired medical illustration"
}}

Return ONLY valid JSON, no commentary.
""".strip()


def _improve_mcq_with_critique(
    article: Dict[str, Any],
    mcq_json: Dict[str, Any],
    critique: str,
    model_id: Optional[str] = None
) -> Dict[str, Any]:
    """Improve MCQ using critique from LoopAgent.
    
    Args:
        article: Article data with title and content
        mcq_json: Current MCQ JSON payload
        critique: Critique text from LoopAgent
        model_id: Optional model identifier. If contains "chatgpt" or "openai", uses OpenAI API.
                  Otherwise uses Gemini (default).
        
    Returns:
        Improved MCQ JSON payload
        
    Raises:
        Exception: If LLM API call fails or JSON parsing fails
    """
    prompt = _build_refinement_prompt(critique, mcq_json, article)
    
    # Route to OpenAI if ChatGPT selected, otherwise use Gemini
    if model_id and ("chatgpt" in model_id.lower() or "openai" in model_id.lower()):
        # OpenAI API with JSON mode
        client = _get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a medical MCQ author. Return only valid JSON, no commentary."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        payload = _extract_json_from_response(response, "openai")
    else:
        # Gemini API (default)
        client = _get_gemini_client()
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
        )
        payload = _extract_json_from_response(response, "gemini")
    
    return payload


def regenerate_mcq_with_feedback(article: Dict[str, Any], previous_payload: Dict[str, Any], feedback: str, model_id: Optional[str] = None) -> GeminiResult:
    """Regenerate MCQ using reviewer feedback.
    
    Args:
        article: Article data with title and content
        previous_payload: Previous MCQ JSON payload
        feedback: Reviewer feedback text
        model_id: Optional model identifier. If contains "chatgpt" or "openai", uses OpenAI API.
                  Otherwise uses Gemini (default).
    """
    try:
        prompt = f"""
The reviewer provided feedback for an MCQ. Return updated JSON with the same schema as before.

Feedback:
{feedback}

Previous response JSON:
{json.dumps(previous_payload, ensure_ascii=False)}

Article title: {article.get("title")}
Article snippet:
\"\"\"{article.get("content", "")[:6000]}\"\"\"
"""
        
        # Route to OpenAI if ChatGPT selected, otherwise use Gemini
        if model_id and ("chatgpt" in model_id.lower() or "openai" in model_id.lower()):
            # OpenAI API with JSON mode
            client = _get_openai_client()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a medical MCQ author. Return only valid JSON, no commentary."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            payload = _extract_json_from_response(response, "openai")
            return GeminiResult(True, "MCQ regenerated (ChatGPT)", payload)
        else:
            # Gemini API (default)
            client = _get_gemini_client()
            response = client.models.generate_content(
                model=_GEMINI_MODEL,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
            )
            payload = _extract_json_from_response(response, "gemini")
            return GeminiResult(True, "MCQ regenerated (Gemini)", payload)
    except Exception as exc:  # pragma: no cover
        provider = "ChatGPT" if (model_id and ("chatgpt" in model_id.lower() or "openai" in model_id.lower())) else "Gemini"
        return GeminiResult(False, f"{provider} MCQ regeneration failed: {exc}", None)


def regenerate_mcq_with_loop_refinement(
    article: Dict[str, Any],
    previous_payload: Dict[str, Any],
    feedback: str,
    model_id: Optional[str] = None,
    max_iterations: int = 2
) -> GeminiResult:
    """Regenerate MCQ with LoopAgent refinement (up to 2 iterations).
    
    Attempts LoopAgent (Gemini) critique + Primary LLM improvement loop.
    Falls back to direct feedback method if LoopAgent fails early.
    Returns last good MCQ on any failure.
    
    Args:
        article: Article data with title and content
        previous_payload: Previous MCQ JSON payload
        feedback: Reviewer feedback text
        model_id: Optional model identifier for Primary LLM (LoopAgent always uses Gemini).
                  If contains "chatgpt" or "openai", uses OpenAI API. Otherwise uses Gemini (default).
        max_iterations: Maximum number of refinement iterations (default: 2)
        
    Returns:
        GeminiResult with improved MCQ payload or fallback to direct feedback result
    """
    last_good_mcq = previous_payload  # Track last valid MCQ
    
    # ITERATION 1
    try:
        # Step 1: Get critique from LoopAgent (Gemini)
        critique = _get_critique_from_loopagent(previous_payload, feedback)
    except Exception as exc:
        # EARLY FAILURE: Fallback to old method (no critique)
        return regenerate_mcq_with_feedback(article, previous_payload, feedback, model_id)
    
    try:
        # Step 2: Primary LLM improves MCQ with critique
        improved_mcq = _improve_mcq_with_critique(article, previous_payload, critique, model_id)
        last_good_mcq = improved_mcq  # Update last good
    except Exception:
        # Return last good MCQ (original)
        return GeminiResult(True, "MCQ update (fallback to original)", last_good_mcq)
    
    # ITERATION 2 (if max_iterations >= 2)
    if max_iterations >= 2:
        try:
            # Step 3: Get second critique
            critique2 = _get_critique_from_loopagent(last_good_mcq, feedback)
        except Exception:
            # Return last good MCQ (from iteration 1)
            return GeminiResult(True, "MCQ updated (1 iteration)", last_good_mcq)
        
        try:
            # Step 4: Primary LLM improves again
            final_mcq = _improve_mcq_with_critique(article, last_good_mcq, critique2, model_id)
            return GeminiResult(True, "MCQ updated (2 iterations)", final_mcq)
        except Exception:
            # Return last good MCQ (from iteration 1)
            return GeminiResult(True, "MCQ updated (1 iteration, fallback)", last_good_mcq)
    
    return GeminiResult(True, "MCQ updated (1 iteration)", last_good_mcq)

