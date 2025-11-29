"""Image generation helper supporting both Gemini and OpenAI (DALL-E)."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from io import BytesIO
from math import gcd
from typing import Optional, Tuple

import requests
from google import genai
from google.genai import types
from openai import OpenAI
from PIL import Image

DEFAULT_IMAGE_SIZE = os.getenv("GEMINI_IMAGE_DEFAULT_SIZE", "512x512")
IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

# Retry config for image generation (1 initial call + 1 retry = 2 attempts max)
# Only retry on genuine server errors, NOT rate limits (429) or connection issues
_IMAGE_RETRY_CONFIG = types.HttpRetryOptions(
    attempts=2,  # 1 initial + 1 retry
    exp_base=2,  # Not used with only 1 retry, but set for consistency
    initial_delay=2,  # 2 second delay before retry
    http_status_codes=[500, 503, 504],  # Only retry on server errors (500, 503, 504)
    # Excluded: 429 (rate limit - don't retry, wastes quota)
    # Excluded: Connection errors handled by exception handling
)


@dataclass
class GeminiImageResult:
    success: bool
    message: str
    image_bytes: Optional[bytes] = None
    size_used: Optional[str] = None


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


def _parse_size_to_image_config(size_value: str) -> Tuple[types.ImageConfig, Optional[Tuple[int, int]]]:
    """Coerce user-provided size into an aspect ratio; keep dims for local resizing."""
    normalized = (size_value or "").strip() or DEFAULT_IMAGE_SIZE or "512x512"
    normalized = normalized.lower()

    if "x" in normalized:
        width_str, height_str = normalized.split("x", 1)
        try:
            width = max(32, min(2048, int(width_str)))
            height = max(32, min(2048, int(height_str)))
            divisor = gcd(width, height) or 1
            ratio = f"{width // divisor}:{height // divisor}"
            return types.ImageConfig(aspect_ratio=ratio), (width, height)
        except ValueError:
            return types.ImageConfig(aspect_ratio="1:1"), None

    if ":" in normalized:
        return types.ImageConfig(aspect_ratio=normalized), None

    return types.ImageConfig(aspect_ratio="1:1"), None


def _extract_image_bytes(response) -> Optional[bytes]:
    """Safely pull inline image bytes from a Gemini response."""
    if not response:
        return None

    candidate_sequences = []
    parts_attr = getattr(response, "parts", None)
    if parts_attr:
        candidate_sequences.append(parts_attr)

    candidates = getattr(response, "candidates", None)
    if candidates:
        for candidate in candidates:
            if getattr(candidate, "content", None) and getattr(candidate.content, "parts", None):
                candidate_sequences.append(candidate.content.parts)
            elif getattr(candidate, "parts", None):
                candidate_sequences.append(candidate.parts)

    for sequence in candidate_sequences:
        for part in sequence:
            inline_data = getattr(part, "inline_data", None)
            if inline_data and getattr(inline_data, "data", None):
                data = inline_data.data
                if isinstance(data, bytes):
                    return data
                if isinstance(data, str):
                    try:
                        return base64.b64decode(data)
                    except Exception:
                        return data.encode("utf-8")
    return None


def generate_image_from_prompt(prompt: str, size: Optional[str] = None, model_id: Optional[str] = None) -> GeminiImageResult:
    """Generate an image using Gemini or OpenAI DALL-E.
    
    Args:
        prompt: Visual prompt text
        size: Image size (e.g., "512x512")
        model_id: Optional model identifier. If contains "chatgpt" or "openai", uses DALL-E API.
                  Otherwise uses Gemini (default).
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return GeminiImageResult(False, "Provide a visual prompt before generating.", None)

    resolved_size = (size or DEFAULT_IMAGE_SIZE or "").strip() or "300x300"

    try:
        # Route to OpenAI DALL-E if ChatGPT selected, otherwise use Gemini
        if model_id and ("chatgpt" in model_id.lower() or "openai" in model_id.lower()):
            # OpenAI DALL-E API - use same approach as Gemini: parse size, use supported API size, resize locally
            client = _get_openai_client()
            
            # Parse requested size to get target dimensions (like Gemini does)
            width_str, height_str = resolved_size.split("x", 1) if "x" in resolved_size else ("512", "512")
            try:
                target_width = max(32, min(2048, int(width_str)))
                target_height = max(32, min(2048, int(height_str)))
            except ValueError:
                target_width, target_height = 512, 512
            
            # Map to OpenAI supported sizes: "1024x1024", "1024x1536", "1536x1024", or "auto"
            # Use aspect ratio to determine best match, then resize locally
            aspect_ratio = target_width / target_height if target_height > 0 else 1.0
            
            if abs(aspect_ratio - 1.0) < 0.1:  # Square-ish (1:1)
                openai_size = "1024x1024"
            elif aspect_ratio < 1.0:  # Portrait (height > width)
                openai_size = "1024x1536"
            elif aspect_ratio > 1.0:  # Landscape (width > height)
                openai_size = "1536x1024"
            else:
                openai_size = "1024x1024"  # Default to square
            
            response = client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size=openai_size,
                n=1,
            )
            
            # Extract image data - gpt-image-1 returns base64 in b64_json field
            image_data = response.data[0]
            # Check if b64_json exists (base64), otherwise use url
            if hasattr(image_data, 'b64_json') and image_data.b64_json:
                image_base64 = image_data.b64_json
                image_bytes = base64.b64decode(image_base64)
            elif hasattr(image_data, 'url') and image_data.url:
                # Fallback: download from URL if base64 not available
                img_response = requests.get(image_data.url)
                image_bytes = img_response.content
            else:
                raise ValueError("No image data found in response")
            
            # Resize to requested dimensions (same as Gemini approach)
            try:
                pil_image = Image.open(BytesIO(image_bytes))
                pil_image = pil_image.convert("RGBA")
                # Always resize to target dimensions (like Gemini does)
                if pil_image.size != (target_width, target_height):
                    pil_image = pil_image.resize((target_width, target_height), Image.LANCZOS)
                buffer = BytesIO()
                pil_image.save(buffer, format="PNG")
                image_bytes = buffer.getvalue()
            except Exception:
                # Fall back to original bytes if resizing fails
                pass
            
            return GeminiImageResult(True, "Image generated successfully (DALL-E).", image_bytes, resolved_size)
        else:
            # Gemini API (default)
            client = _get_gemini_client()
            image_config, resize_dims = _parse_size_to_image_config(resolved_size)
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=image_config,
                    http_retry_options=_IMAGE_RETRY_CONFIG,
                ),
            )
            image_bytes = _extract_image_bytes(response)
            if not image_bytes:
                return GeminiImageResult(False, "Gemini did not return image data.", None)

            if resize_dims:
                try:
                    pil_image = Image.open(BytesIO(image_bytes))
                    pil_image = pil_image.convert("RGBA")
                    pil_image = pil_image.resize(resize_dims, Image.LANCZOS)
                    buffer = BytesIO()
                    # Default to PNG for consistency
                    pil_image.save(buffer, format="PNG")
                    image_bytes = buffer.getvalue()
                except Exception:
                    # Fall back to original bytes if resizing fails
                    pass

            return GeminiImageResult(True, "Image generated successfully (Gemini).", image_bytes, resolved_size)
    except Exception as exc:  # pragma: no cover - relies on external service
        provider = "DALL-E" if (model_id and ("chatgpt" in model_id.lower() or "openai" in model_id.lower())) else "Gemini"
        return GeminiImageResult(False, f"{provider} image generation failed: {exc}", None)
