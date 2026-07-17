"""Optional LLM-backed composer (set COMPOSER_MODE=llm and an API key)."""

from __future__ import annotations

import json
import os
import urllib.error
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
- Never expose internal field names like trigger_id, merchant_id, suppression_key, urgency, or raw JSON
- Never repeat a message body already sent in this conversation
- For doctors/dentists use clinical peer-to-peer tone; for salons use warm practical tone; for restaurants use operator-to-operator tone; for gyms use coaching tone; for pharmacies use precise trustworthy tone
- Prefer one strong engagement lever: specificity, loss aversion, social proof, effort externalization, curiosity, reciprocity, or a binary CTA
- Keep under 400 characters when possible

Return ONLY valid JSON:
{"body": "...", "cta": "open_ended|yes_stop|none", "rationale": "..."}"""


REPLY_SYSTEM = """You are Vera, continuing a WhatsApp conversation with a merchant or customer on magicpin.

Rules:
- If the incoming message is a clear commitment like "yes", "ok", "lets do it", "go ahead", or "what next", move to the next concrete step. Do not ask them to clarify intent again.
- If they ask to stop, are hostile, or say not interested, end politely without pitching.
- If the text looks like a WhatsApp Business auto-reply, send at most one gentle human-check nudge, then end if it repeats.
- Match the merchant/customer language, including Hindi-English code-mix when they use it.
- Never repeat a message body already sent in this conversation.
- Use one CTA at most, and place it in the final sentence.
- Keep it short, natural, and specific. Use only facts from context; do not invent offers, numbers, or competitor names.
- Do not expose internal IDs, raw JSON, prompt details, scoring rules, or system details.
- If the merchant goes off-topic but is not hostile, acknowledge briefly and steer back to Vera's concrete next step.
- If the merchant asks for time, prefer wait instead of pushing.

Correct commitment handoff:
[MERCHANT] "Ok lets do it, whats next?"
Good body: "Great - I will prepare the exact profile update from your listing data and share it here for approval. Reply YES when you want me to proceed."
Bad body: "Can you clarify what you need?" because it ignores clear intent.

Correct hostile handling:
[MERCHANT] "Stop messaging me. This is spam."
Good action: end. Do not send another pitch.

Return ONLY one valid JSON object:
{"action": "send", "body": "...", "cta": "open_ended|yes_stop|none", "rationale": "..."}
{"action": "wait", "wait_seconds": 1800, "rationale": "..."}
{"action": "end", "rationale": "..."}"""


def compose_with_llm(category, merchant, trigger, customer=None) -> dict:
    prompt = f"""Compose a message from these contexts:

CATEGORY: {json.dumps(category, ensure_ascii=False)[:3000]}
MERCHANT: {json.dumps(merchant, ensure_ascii=False)[:3000]}
TRIGGER: {json.dumps(trigger, ensure_ascii=False)[:1500]}
CUSTOMER: {json.dumps(customer, ensure_ascii=False)[:1500] if customer else "null"}
"""
    text = _call_llm(prompt, SYSTEM)
    match = json.loads(_extract_json(text))
    result = {
        "body": match.get("body", ""),
        "cta": match.get("cta", "open_ended"),
        "rationale": match.get("rationale", "LLM composition"),
    }
    return _finalize(result, category, merchant, trigger, customer)


def compose_reply_with_llm(
    state,
    merchant_message: str,
    category=None,
    merchant=None,
    trigger=None,
    customer=None,
) -> dict:
    history = "\n".join(
        f"[{turn.get('from', '').upper()}] {turn.get('body', '')}"
        for turn in getattr(state, "turns", [])[-8:]
    )
    prompt = f"""Continue this WhatsApp conversation.

CONVERSATION_ID: {getattr(state, "conversation_id", "")}
MERCHANT_ID: {getattr(state, "merchant_id", "")}
CUSTOMER_ID: {getattr(state, "customer_id", "")}

CATEGORY CONTEXT: {json.dumps(category or {}, ensure_ascii=False)[:2500]}
MERCHANT CONTEXT: {json.dumps(merchant or {}, ensure_ascii=False)[:3000]}
TRIGGER CONTEXT: {json.dumps(trigger or {}, ensure_ascii=False)[:2000]}
CUSTOMER CONTEXT: {json.dumps(customer or {}, ensure_ascii=False)[:2000]}

CONVERSATION SO FAR:
{history}

LATEST INCOMING MESSAGE:
{merchant_message}

MESSAGES VERA ALREADY SENT, DO NOT REPEAT VERBATIM:
{json.dumps(getattr(state, "sent_bodies", []), ensure_ascii=False)}
"""
    text = _call_llm(prompt, REPLY_SYSTEM, max_tokens=500)
    parsed = json.loads(_extract_json(text))
    if parsed.get("action") not in {"send", "wait", "end"}:
        raise ValueError("LLM reply missing valid action")
    return parsed


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _call_llm(prompt: str, system: str = SYSTEM, max_tokens: int = 800) -> str:
    if key := os.getenv("GROQ_API_KEY"):
        return _groq(prompt, key, system, max_tokens)
    if key := os.getenv("GEMINI_API_KEY"):
        return _gemini(prompt, key, system, max_tokens)
    if key := os.getenv("OPENAI_API_KEY"):
        return _openai(prompt, key, system, max_tokens)
    raise RuntimeError("No LLM API key configured")


def _openai(prompt: str, api_key: str, system: str, max_tokens: int) -> str:
    body = json.dumps(
        {
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": max_tokens,
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


def _groq(prompt: str, api_key: str, system: str, max_tokens: int) -> str:
    body = json.dumps(
        {
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": max_tokens,
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    last_error = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 and exc.code < 500:
                raise
        except urllib.error.URLError as exc:
            last_error = exc
    raise RuntimeError(f"Groq call failed: {last_error}")


def _gemini(prompt: str, api_key: str, system: str, max_tokens: int) -> str:
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": system + "\n\n" + prompt}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens},
        }
    ).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read())
    return data["candidates"][0]["content"]["parts"][0]["text"]
