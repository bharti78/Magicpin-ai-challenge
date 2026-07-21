from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("uvicorn.error")

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

OFF_TOPIC_PATTERNS = [
    r"\b(cricket score|stock tip|crypto|bitcoin|weather|news|joke|recipe|homework)\b",
]

TECHNICAL_XRAY_PATTERNS = [
    r"\b(x-?ray|radiograph|iopa|d-?speed|e-?speed|rvg|dose|sensor)\b",
]

TECHNICAL_FOLLOWUP_PATTERNS = [
    r"\b(schedule h1|h1 register|prescription|cold chain|gst|fssai|hygiene|food license)\b",
    r"\b(retinol|patch test|keratin|colour|color|allergy|sterilization)\b",
    r"\b(bmi|injury|physio|trial class|membership|trainer|form check)\b",
    r"\b(menu|swiggy|zomato|combo|food safety|kitchen|packaging)\b",
]

SLOT_PATTERNS = [
    r"\b(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b\d{1,2}\s*(am|pm)\b",
    r"\b\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\b",
    r"\b(book|slot|appointment|confirm|reschedule)\b",
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
    last_incoming_text: str = ""
    repeat_count: int = 0
    ended: bool = False
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


def is_off_topic(message: str) -> bool:
    return _matches(message, OFF_TOPIC_PATTERNS)


def is_technical_xray_followup(message: str) -> bool:
    return _matches(message, TECHNICAL_XRAY_PATTERNS)


def is_technical_followup(message: str) -> bool:
    return _matches(message, TECHNICAL_FOLLOWUP_PATTERNS)


def is_slot_reply(message: str) -> bool:
    return _matches(message, SLOT_PATTERNS)


def _limit(text: str, max_chars: int = 320) -> str:
    clean = " ".join(text.strip().split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rsplit(" ", 1)[0] + "..."


def _slot_summary(message: str) -> str:
    cleaned = message.strip().strip(".")
    match = re.search(r"\bfor\s+(.+)$", cleaned, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(
        r"\b((?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\s+\d{1,2}\s+\w+,\s*\d{1,2}\s*(?:am|pm))\b",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    if is_commitment(cleaned):
        return "selected slot"
    return cleaned


def _llm_enabled() -> bool:
    mode = os.getenv("REPLY_MODE", os.getenv("COMPOSER_MODE", "template")).lower()
    has_key = bool(os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))
    return mode == "llm" and has_key


def _merchant_name(merchant: dict | None) -> str:
    return (merchant or {}).get("identity", {}).get("name", "your business")


def _merchant_metric_line(merchant: dict | None) -> str:
    perf = (merchant or {}).get("performance", {})
    bits = []
    if perf.get("views") is not None:
        bits.append(f"{perf['views']} views")
    if perf.get("calls") is not None:
        bits.append(f"{perf['calls']} calls")
    if perf.get("directions") is not None:
        bits.append(f"{perf['directions']} directions")
    return ", ".join(bits[:2])


def _active_offer(merchant: dict | None) -> str:
    for offer in (merchant or {}).get("offers", []) or []:
        if offer.get("status") == "active" and offer.get("title"):
            return offer["title"]
    return ""


def _next_step_topic(trigger: dict | None) -> str:
    payload = (trigger or {}).get("payload", {})
    topic = payload.get("intent_topic") or payload.get("metric_or_topic") or (trigger or {}).get("kind", "profile update")
    return str(topic).replace("_", " ")


def _offer_fits_topic(topic: str) -> bool:
    blocked = ("verification", "compliance", "audit", "sop", "regulation", "license")
    return not any(word in topic.lower() for word in blocked)


def _technical_reply(category: dict | None, merchant: dict | None) -> str:
    slug = (category or {}).get("slug") or (merchant or {}).get("category_slug", "")
    metrics = _merchant_metric_line(merchant)
    offer = _active_offer(merchant)

    if slug == "pharmacies":
        return (
            f"For {_merchant_name(merchant)}, keep refill/H1 replies safe: ask for valid prescription, "
            "log batch/expiry, and avoid dosage advice on WhatsApp. "
            f"{'Use ' + offer + ' only after stock check. ' if offer else ''}Want a 5-point SOP?"
        )
    if slug == "salons":
        return (
            "For salon replies, mention patch test before colour/keratin, avoid medical claims, "
            f"and anchor on {offer or 'the booked service'}. "
            "Main review-safe WhatsApp + Google Post draft kar doon?"
        )
    if slug == "gyms":
        return (
            "For gym follow-up: goal, injury check, beginner slot, then trainer consult. "
            f"{'Your 30d signal: ' + metrics + '. ' if metrics else ''}Want a trial-class script?"
        )
    if slug == "restaurants":
        return (
            "For restaurant campaigns: hero item, prep capacity, delivery radius, FSSAI-safe copy. "
            f"{'Use ' + offer + ' as anchor. ' if offer else ''}Want a 3-line combo draft?"
        )
    return (
        f"For {_merchant_name(merchant)}, I can help within profile, campaign, customer follow-up, or compliance scope. "
        "Tell me the service/topic and I will draft the next step."
    )


def respond_customer(
    state: ConversationState,
    customer_message: str,
    category: dict | None = None,
    merchant: dict | None = None,
    trigger: dict | None = None,
    customer: dict | None = None,
) -> dict:
    """Produce the next action for a customer's reply to merchant outreach."""
    if state.ended:
        return {"action": "end", "rationale": "Conversation already ended"}

    incoming = customer_message.strip()
    state.turns.append({"from": "customer", "body": customer_message})

    if is_hostile(incoming) or is_not_interested(incoming):
        state.ended = True
        return {"action": "end", "rationale": "Customer opted out or declined; ending immediately"}

    if is_auto_reply(incoming):
        state.ended = True
        return {"action": "end", "rationale": "Customer auto-reply detected; no follow-up needed"}

    merchant_name = (merchant or {}).get("identity", {}).get("name", "clinic")
    customer_name = (customer or {}).get("identity", {}).get("name", "")
    prefix = f"{customer_name}, " if customer_name else ""

    if is_slot_reply(incoming) or is_commitment(incoming):
        slot = _slot_summary(incoming)
        body = (
            f"{prefix}noted - {slot} ke liye request {merchant_name} ko bhej di hai. "
            "Clinic final confirmation share karega. Reschedule chahiye ho to alternate time bhej dein."
        )
        return {
            "action": "send",
            "body": _limit(body),
            "cta": "none",
            "rationale": "Customer picked or accepted an appointment slot; acknowledged booking request",
        }

    if "?" in incoming:
        body = (
            f"{prefix}{merchant_name} se confirm karke batate hain. "
            "Appointment ke liye apna preferred day/time bhej dein, main request forward kar dunga."
        )
        return {
            "action": "send",
            "body": _limit(body),
            "cta": "open_ended",
            "rationale": "Customer asked a question; steering to a bookable next step",
        }

    return {
        "action": "send",
        "body": _limit(
            f"{prefix}thanks, message {merchant_name} ko forward kar diya hai. "
            "Booking ke liye preferred day/time bhej dein."
        ),
        "cta": "open_ended",
        "rationale": "Customer reply acknowledged with booking-oriented next step",
    }


def respond(
    state: ConversationState,
    merchant_message: str,
    category: dict | None = None,
    merchant: dict | None = None,
    trigger: dict | None = None,
    customer: dict | None = None,
) -> dict:
    """Produce the next bot action given conversation state and inbound message."""
    if state.ended:
        return {"action": "end", "rationale": "Conversation already ended"}

    incoming = merchant_message.strip()
    if state.last_incoming_text == incoming:
        state.repeat_count += 1
    else:
        state.repeat_count = 0
    state.last_incoming_text = incoming

    state.turns.append({"from": "merchant", "body": merchant_message})

    if is_hostile(merchant_message) or is_not_interested(merchant_message):
        state.ended = True
        return {
            "action": "end",
            "rationale": "Merchant signaled stop / not interested — graceful exit",
        }

    if state.repeat_count >= 2:
        state.ended = True
        return {
            "action": "end",
            "rationale": "Same incoming message repeated 3+ times; treating as automated and exiting",
        }

    if is_auto_reply(merchant_message):
        state.auto_reply_count += 1
        mid = state.merchant_id
        if mid:
            merchant_auto_reply_count[mid] = merchant_auto_reply_count.get(mid, 0) + 1
        total = max(state.auto_reply_count, merchant_auto_reply_count.get(mid or "", 0))
        if total >= 2:
            state.ended = True
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

    if is_off_topic(merchant_message):
        return {
            "action": "send",
            "body": _limit(
                "I can't help with that here. I can help with your magicpin/Google profile, "
                "customer follow-ups, offers, compliance reminders, and campaign drafts. "
                "Which one should I handle?"
            ),
            "cta": "open_ended",
            "rationale": "Unsupported off-topic request declined and routed back to Vera scope",
        }

    if is_technical_xray_followup(merchant_message):
        return {
            "action": "send",
            "body": _limit(
                "Dr., D-speed is the risk: DCI's new 1.0 mSv per IOPA limit starts 15 Dec 2026; "
                "D-speed fails, E-speed passes, RVG is unaffected. "
                "Main audit checklist + SOP line bana doon for your unit?"
            ),
            "cta": "yes_stop",
            "rationale": "Grounded dental radiograph compliance follow-up using category context",
        }

    if is_technical_followup(merchant_message):
        return {
            "action": "send",
            "body": _limit(_technical_reply(category, merchant)),
            "cta": "yes_stop",
            "rationale": "Category-specific technical follow-up instead of generic fallback",
        }

    if is_commitment(merchant_message):
        topic = _next_step_topic(trigger)
        metrics = _merchant_metric_line(merchant)
        offer = _active_offer(merchant) if _offer_fits_topic(topic) else ""
        if state.last_bot_body:
            return {
                "action": "send",
                "body": _limit(
                    f"Great - I will prepare the {topic} draft using "
                    f"{metrics or _merchant_name(merchant)}"
                    f"{' and ' + offer if offer else ''}. Reply YES and I will share the final copy here."
                ),
                "cta": "yes_stop",
                "rationale": "Merchant confirmed intent again; grounded next step",
            }
        return {
            "action": "send",
            "body": _limit(
                f"Done - {topic} pe action mode. "
                f"{'I will use ' + offer + ' as the anchor. ' if offer else ''}"
                "Main exact draft/checklist yahin bhejti hoon; final approve karne ke liye YES."
            ),
            "cta": "yes_stop",
            "rationale": "Explicit commitment detected; switched to grounded action mode",
        }

    if _llm_enabled():
        try:
            from llm_client import compose_reply_with_llm

            result = compose_reply_with_llm(state, merchant_message, category, merchant, trigger, customer)
            if result.get("action") == "send" and not result.get("body"):
                raise ValueError("LLM reply missing body")
            return result
        except Exception as exc:
            logger.warning("LLM reply failed; using deterministic fallback: %s", exc)
            pass

    if is_commitment(merchant_message):
        topic = _next_step_topic(trigger)
        metrics = _merchant_metric_line(merchant)
        offer = _active_offer(merchant)
        if state.last_bot_body:
            return {
                "action": "send",
                "body": _limit(
                    f"Great - I will prepare the {topic} draft using "
                    f"{metrics or _merchant_name(merchant)}"
                    f"{' and ' + offer if offer else ''}. Reply YES and I will share the final copy here."
                ),
                "cta": "yes_stop",
                "rationale": "Merchant confirmed intent again; grounded next step",
            }
        return {
            "action": "send",
            "body": _limit(
                f"Done - {topic} pe action mode. "
                f"{'I will use ' + offer + ' as the anchor. ' if offer else ''}"
                "Main exact draft/checklist yahin bhejti hoon; final approve karne ke liye YES."
            ),
            "cta": "yes_stop",
            "rationale": "Explicit commitment detected; switched to grounded action mode",
        }

    if False and is_commitment(merchant_message):
        if state.last_bot_body:
            return {
                "action": "send",
                "body": (
                    "Great - next step is simple: I will prepare the exact update or draft from "
                    "your profile data and share it here for approval. Reply YES when you want "
                    "me to proceed with the final version."
                ),
                "cta": "yes_stop",
                "rationale": "Merchant confirmed intent again; giving a concrete next step without repeating",
            }
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
        topic = _next_step_topic(trigger)
        metrics = _merchant_metric_line(merchant)
        return {
            "action": "send",
            "body": _limit(
                f"Good question. For {topic}, I will use your "
                f"{metrics or 'merchant profile'} and current offer data, then give one recommended next step. "
                "Should I send that now?"
            ),
            "cta": "open_ended",
            "rationale": "Merchant asked a question; grounded answer framing with advance CTA",
        }

    if False and "?" in merchant_message:
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
