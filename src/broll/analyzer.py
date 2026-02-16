# src/broll/analyzer.py
"""
LLM-powered video content analysis using Ollama vision models.

Sends extracted keyframes to a local vision model (e.g. minicpm-v)
and gets back structured descriptions, tags, mood, etc.
"""
from __future__ import annotations

import base64
import json
import re

import ollama

from .config import VISION_MODEL


ANALYSIS_PROMPT = (
    "You are analyzing keyframes from a b-roll video clip for a video editor's searchable catalog.\n\n"
    "Look at these frames carefully and return ONLY a valid JSON object (no markdown, no explanation) with these exact fields:\n\n"
    "{\n"
    '  "scene_description": "2-3 sentence vivid description of the scene - what is shown, what is happening, the setting",\n'
    '  "tags": ["tag1", "tag2", "tag3"],\n'
    '  "mood": "single mood word or short phrase",\n'
    '  "camera_movement": "one of: static, pan, tilt, tracking, handheld, aerial, gimbal, dolly, zoom, unknown",\n'
    '  "time_of_day": "one of: dawn, morning, midday, afternoon, golden_hour, sunset, blue_hour, night, overcast, indoor, unknown"\n'
    "}\n\n"
    "Guidelines for tags (provide 8-12 tags):\n"
    '- Subject matter (e.g. "people", "ocean", "mountains", "food", "cityscape")\n'
    '- Actions/movement (e.g. "walking", "waves crashing", "cars driving")\n'
    '- Setting type (e.g. "beach", "urban", "forest", "restaurant", "market")\n'
    '- Visual qualities (e.g. "bokeh", "silhouette", "reflections", "lens flare")\n'
    '- Weather/atmosphere (e.g. "sunny", "foggy", "rainy", "cloudy")\n'
    '- Colors (e.g. "warm tones", "blue", "neon", "muted colors")\n\n'
    "Be specific and practical - a video editor needs to find this clip quickly."
)


def analyze_frames(keyframes: list[bytes]) -> dict:
    """
    Send keyframes to the vision LLM for content analysis.

    Args:
        keyframes: List of JPEG image bytes (keyframes from a video).

    Returns:
        Dict with: scene_description, tags, mood, camera_movement, time_of_day
    """
    images_b64 = [base64.b64encode(frame).decode("utf-8") for frame in keyframes]

    try:
        response = ollama.chat(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": ANALYSIS_PROMPT,
                    "images": images_b64,
                }
            ],
            options={
                "temperature": 0.3,
                "num_predict": 1024,
            },
        )

        content = response["message"]["content"]
        return _parse_llm_response(content)

    except ollama.ResponseError as e:
        print(f"  Warning: Ollama API error: {e}")
        return _empty_analysis()
    except Exception as e:
        print(f"  Warning: Analysis error: {e}")
        return _empty_analysis()


def _parse_llm_response(content: str) -> dict:
    """
    Robustly parse the LLM's JSON response.

    Vision models sometimes wrap JSON in markdown code fences,
    add commentary before/after, or produce slightly malformed JSON.
    """
    content = content.strip()

    # Strip markdown code fences if present
    if "```" in content:
        match = re.search(r'```(?:json)?\s*\n?(.*?)```', content, re.DOTALL)
        if match:
            content = match.group(1).strip()

    # Try direct JSON parse first
    try:
        parsed = json.loads(content)
        return _validate_analysis(parsed)
    except json.JSONDecodeError:
        pass

    # Fallback: try to find a JSON object anywhere in the response
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            return _validate_analysis(parsed)
        except json.JSONDecodeError:
            pass

    # Fallback: try to find JSON with nested arrays
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            return _validate_analysis(parsed)
        except json.JSONDecodeError:
            pass

    # Last resort: use the raw text as the description
    print('  Warning: Could not parse LLM response as JSON, using raw text')
    return {
        'scene_description': content[:500],
        'tags': [],
        'mood': 'unknown',
        'camera_movement': 'unknown',
        'time_of_day': 'unknown',
    }


def _validate_analysis(parsed: dict) -> dict:
    '''Ensure the parsed response has all required fields with correct types.'''
    result = {}

    result['scene_description'] = str(parsed.get('scene_description', ''))[:1000]

    tags = parsed.get('tags', [])
    if isinstance(tags, list):
        result['tags'] = [str(t).strip() for t in tags if t]
    elif isinstance(tags, str):
        result['tags'] = [t.strip() for t in tags.split(',') if t.strip()]
    else:
        result['tags'] = []

    result['mood'] = str(parsed.get('mood', 'unknown')).strip()

    valid_movements = {
        'static', 'pan', 'tilt', 'tracking', 'handheld',
        'aerial', 'gimbal', 'dolly', 'zoom', 'unknown',
    }
    movement = str(parsed.get('camera_movement', 'unknown')).strip().lower()
    result['camera_movement'] = movement if movement in valid_movements else 'unknown'

    valid_times = {
        'dawn', 'morning', 'midday', 'afternoon', 'golden_hour',
        'sunset', 'blue_hour', 'night', 'overcast', 'indoor', 'unknown',
    }
    time_of_day = str(parsed.get('time_of_day', 'unknown')).strip().lower()
    result['time_of_day'] = time_of_day if time_of_day in valid_times else 'unknown'

    return result


def _empty_analysis() -> dict:
    '''Return an empty analysis result when the LLM fails.'''
    return {
        'scene_description': '',
        'tags': [],
        'mood': 'unknown',
        'camera_movement': 'unknown',
        'time_of_day': 'unknown',
    }
