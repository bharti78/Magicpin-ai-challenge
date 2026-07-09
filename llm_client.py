"""Optional LLM-backed composer (set COMPOSER_MODE=llm and an API key)."""

from __future__ import annotations

import json
import os
import urllib.request

from composer import _finalize


SYSTEM = """You compose WhatsApp messages for Vera, magicpin's merchant AI assistant.

Rules:
- Anchor on verifiable facts from the provided contexts only — never invent data
- Match category voice (clinical for dentists, warm for salons, etc.)
- Personalize to this merchant's numbers, offers, locality, language
- Explain WHY NOW based on the trigger
- Use Hindi-English code-mix when merchant languages include "hi" or customer language_pref has "hi"
- Service+price offers over generic discounts ("Haircut @ ₹99" not "10% off")
- Single primary CTA at the end
- No long preambles, no re-introductions
- Keep under 400 characters when possible

Return ONLY valid JSON:
{"body": "...", "cta": "open_ended|yes_stop|none", "rationale": "..."}"""


def compose_with_llm(category, merchant, trigger, customer=None) -> dict:
    prompt = f"""Compose a message from these contexts:

CATEGORY: {json.dumps(category, ensure_ascii=False)[:3000]}
MERCHANT: {json.dumps(merchant, ensure_ascii=False)[:3000]}
TRIGGER: {json.dumps(trigger, ensure_ascii=False)[:1500]}
CUSTOMER: {json.dumps(customer, ensure_ascii=False)[:1500] if customer else "null"}
"""
    text = _call_llm(prompt)
    match = json.loads(_extract_json(text))
    result = {
        "body": match.get("body", ""),
        "cta": match.get("cta", "open_ended"),
        "rationale": match.get("rationale", "LLM composition"),
    }
    return _finalize(result, category, merchant, trigger, customer)


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _call_llm(prompt: str) -> str:
    if key := os.getenv("GEMINI_API_KEY"):
        return _gemini(prompt, key)
    if key := os.getenv("OPENAI_API_KEY"):
        return _openai(prompt, key)
    raise RuntimeError("No LLM API key configured")


def _openai(prompt: str, api_key: str) -> str:
    body = json.dumps(
        {
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 800,
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def _gemini(prompt: str, api_key: str) -> str:
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": SYSTEM + "\n\n" + prompt}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 800},
        }
    ).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read())
    return data["candidates"][0]["content"]["parts"][0]["text"]
