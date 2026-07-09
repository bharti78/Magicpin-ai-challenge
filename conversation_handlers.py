from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

AUTO_REPLY_PATTERNS = [
    r"thank you for contacting",
    r"our team will respond",
    r"automated assistant",
    r"bahut.?bahut shukriya",
    r"team tak pahuncha",
    r"we('ll| will) get back",
    r"outside (of )?business hours",
]

COMMITMENT_PATTERNS = [
    r"\b(yes|haan|ha|ok|okay|sure|go ahead|let'?s do it|chalega|bhej do|kar do|start)\b",
    r"\bwhat'?s next\b",
    r"\bmujhe .* join\b",
    r"\bupdate my (google )?profile\b",
]

HOSTILE_PATTERNS = [
    r"\b(stop|unsubscribe|spam|useless|band karo|mat bhejo)\b",
    r"\b(not interested|don'?t message)\b",
]

NOT_INTERESTED = [
    r"\bno thanks\b",
    r"\bnot now\b",
    r"\bbadme\b",
    r"\blater\b",
    r"\bnahi\b",
]


merchant_auto_reply_count: dict[str, int] = {}


def reset_merchant_tracking() -> None:
    merchant_auto_reply_count.clear()


@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    trigger_id: str | None = None
    turns: list[dict[str, Any]] = field(default_factory=list)
    auto_reply_count: int = 0
    last_bot_body: str = ""
    sent_bodies: list[str] = field(default_factory=list)


def _matches(text: str, patterns: list[str]) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in patterns)


def is_auto_reply(message: str) -> bool:
    return _matches(message, AUTO_REPLY_PATTERNS)


def is_commitment(message: str) -> bool:
    return _matches(message, COMMITMENT_PATTERNS)


def is_hostile(message: str) -> bool:
    return _matches(message, HOSTILE_PATTERNS)


def is_not_interested(message: str) -> bool:
    return _matches(message, NOT_INTERESTED)


def respond(state: ConversationState, merchant_message: str) -> dict:
    """Produce the next bot action given conversation state and inbound message."""
    state.turns.append({"from": "merchant", "body": merchant_message})

    if is_hostile(merchant_message) or is_not_interested(merchant_message):
        return {
            "action": "end",
            "rationale": "Merchant signaled stop / not interested — graceful exit",
        }

    if is_auto_reply(merchant_message):
        state.auto_reply_count += 1
        mid = state.merchant_id
        if mid:
            merchant_auto_reply_count[mid] = merchant_auto_reply_count.get(mid, 0) + 1
        total = max(state.auto_reply_count, merchant_auto_reply_count.get(mid or "", 0))
        if total >= 1:
            return {
                "action": "end",
                "rationale": "Detected auto-reply pattern — exiting to avoid wasted turns",
            }
        return {
            "action": "send",
            "body": (
                "Samajh gayi — lagta hai yeh auto-reply hai. "
                "Agar aap owner/manager hain, bas 'hi' likh dein — main exact audit bhej dungi. "
                "Warna main baad mein try karungi. 🙂"
            ),
            "cta": "open_ended",
            "rationale": "Auto-reply detected — one human check before exit",
        }

    if is_commitment(merchant_message):
        return {
            "action": "send",
            "body": (
                "Done — shuru karte hain. Main abhi draft bhej rahi hoon. "
                "2 minute mein ready hoga; aap bas review karke YES bolein."
            ),
            "cta": "yes_stop",
            "rationale": "Explicit commitment detected — switched to action mode immediately",
        }

    if "time" in merchant_message.lower() or "wait" in merchant_message.lower():
        return {
            "action": "wait",
            "wait_seconds": 1800,
            "rationale": "Merchant asked for time — backing off 30 minutes",
        }

    if "?" in merchant_message:
        return {
            "action": "send",
            "body": (
                "Good question — main aapke profile data ke basis pe answer karti hoon. "
                "Specifically, aapka Google listing aur recent performance numbers dekh ke "
                "sabse pehla step suggest karungi. Chalega?"
            ),
            "cta": "open_ended",
            "rationale": "Merchant asked a question — answer framing + advance CTA",
        }

    return {
        "action": "send",
        "body": (
            "Noted. Main next step draft kar rahi hoon — aapko 1-2 options bhejungi, "
            "bas YES bolna hai jahan se start karna ho."
        ),
        "cta": "open_ended",
        "rationale": "Default acknowledgment with low-friction forward motion",
    }
