"""Vera merchant AI assistant — HTTP server + compose() entry point."""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

from composer import compose as compose_message
from conversation_handlers import ConversationState, reset_merchant_tracking, respond

app = FastAPI(title="Vera Challenge Bot")
START = time.time()
logger = logging.getLogger("uvicorn.error")

contexts: dict[tuple[str, str], dict] = {}
conversations: dict[str, ConversationState] = {}
suppression_sent: set[str] = set()
active_conversations: set[str] = set()


def _server_port() -> int:
    try:
        return int(os.environ.get("PORT", 8080))
    except ValueError:
        return 8080


def compose(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: dict | None = None,
) -> dict:
    """Public compose API for submission and testing."""
    return compose_message(category, merchant, trigger, customer)


def _get_context(scope: str, context_id: str) -> dict | None:
    entry = contexts.get((scope, context_id))
    return entry["payload"] if entry else None


def _resolve_contexts(trigger: dict) -> tuple[dict | None, dict | None, dict | None, dict | None]:
    merchant_id = trigger.get("merchant_id")
    customer_id = trigger.get("customer_id")
    merchant = _get_context("merchant", merchant_id) if merchant_id else None
    customer = _get_context("customer", customer_id) if customer_id else None
    category = None
    if merchant:
        category = _get_context("category", merchant.get("category_slug", ""))
    if not category:
        payload = trigger.get("payload") or {}
        cat_slug = payload.get("category")
        if cat_slug:
            category = _get_context("category", cat_slug)
    return category, merchant, trigger, customer


def _template_name(trigger: dict, send_as: str) -> str:
    kind = trigger.get("kind", "generic")
    prefix = "merchant" if send_as == "merchant_on_behalf" else "vera"
    return f"{prefix}_{kind}_v1"


@app.get("/v1/healthz")
async def healthz():
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _), _ in contexts.items():
        if scope in counts:
            counts[scope] += 1
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START),
        "contexts_loaded": counts,
    }


@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": "Vera Challenge",
        "team_members": ["Participant"],
        "model": "template-composer-v1",
        "approach": "Trigger-routed deterministic composer with multi-turn reply handlers",
        "contact_email": "team@example.com",
        "version": "1.0.0",
        "submitted_at": datetime.utcnow().isoformat() + "Z",
    }


class CtxBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


@app.exception_handler(RequestValidationError)
async def log_validation_exception(request: Request, exc: RequestValidationError):
    if request.url.path == "/v1/context":
        try:
            raw = await request.json()
        except Exception:
            raw = {}
        payload = raw.get("payload") if isinstance(raw, dict) else None
        payload_keys = sorted(payload.keys()) if isinstance(payload, dict) else []
        logger.warning(
            "context validation failed: scope=%s context_id=%s payload_keys=%s errors=%s",
            raw.get("scope") if isinstance(raw, dict) else None,
            raw.get("context_id") if isinstance(raw, dict) else None,
            payload_keys,
            exc.errors(),
        )
    return await request_validation_exception_handler(request, exc)


@app.post("/v1/context")
async def push_context(body: CtxBody):
    logger.info(
        "context incoming: scope=%s context_id=%s payload_keys=%s",
        body.scope,
        body.context_id,
        sorted(body.payload.keys()),
    )
    if body.scope not in {"category", "merchant", "customer", "trigger"}:
        logger.warning(
            "context rejected: reason=invalid_scope scope=%s context_id=%s",
            body.scope,
            body.context_id,
        )
        return {"accepted": False, "reason": "invalid_scope", "details": body.scope}

    key = (body.scope, body.context_id)
    cur = contexts.get(key)
    if cur and cur["version"] > body.version:
        logger.warning(
            "context rejected: reason=stale_version scope=%s context_id=%s incoming_version=%s current_version=%s",
            body.scope,
            body.context_id,
            body.version,
            cur["version"],
        )
        return {"accepted": False, "reason": "stale_version", "current_version": cur["version"]}
    if cur and cur["version"] == body.version:
        logger.info(
            "context accepted: reason=duplicate_version scope=%s context_id=%s version=%s",
            body.scope,
            body.context_id,
            body.version,
        )
        return {
            "accepted": True,
            "ack_id": f"ack_{body.context_id}_v{body.version}",
            "stored_at": datetime.utcnow().isoformat() + "Z",
        }

    contexts[key] = {"version": body.version, "payload": body.payload}
    logger.info(
        "context accepted: reason=stored scope=%s context_id=%s version=%s",
        body.scope,
        body.context_id,
        body.version,
    )
    return {
        "accepted": True,
        "ack_id": f"ack_{body.context_id}_v{body.version}",
        "stored_at": datetime.utcnow().isoformat() + "Z",
    }


class TickBody(BaseModel):
    now: str
    available_triggers: list[str] = []


@app.post("/v1/tick")
async def tick(body: TickBody):
    actions = []
    ranked: list[tuple[int, str]] = []

    for trg_id in body.available_triggers:
        trg = _get_context("trigger", trg_id)
        if not trg:
            continue
        sk = trg.get("suppression_key", trg_id)
        if sk in suppression_sent:
            continue
        mid = trg.get("merchant_id", "")
        conv_key = f"conv_{mid}_{trg_id}"
        if conv_key in active_conversations:
            continue
        ranked.append((int(trg.get("urgency", 1)), trg_id))

    ranked.sort(key=lambda x: -x[0])

    for _, trg_id in ranked[:20]:
        trg = _get_context("trigger", trg_id)
        if not trg:
            continue
        category, merchant, trigger, customer = _resolve_contexts(trg)
        if not category or not merchant:
            continue

        composed = compose_message(category, merchant, trigger, customer)
        sk = composed.get("suppression_key", trg_id)
        if sk in suppression_sent:
            continue

        conv_id = f"conv_{trg.get('merchant_id')}_{trg_id}_{uuid.uuid4().hex[:6]}"
        state = ConversationState(
            conversation_id=conv_id,
            merchant_id=trg.get("merchant_id"),
            customer_id=trg.get("customer_id"),
            trigger_id=trg_id,
        )
        state.last_bot_body = composed["body"]
        state.sent_bodies.append(composed["body"])
        conversations[conv_id] = state
        active_conversations.add(f"conv_{trg.get('merchant_id')}_{trg_id}")
        suppression_sent.add(sk)

        owner = merchant.get("identity", {}).get("owner_first_name", "")
        actions.append(
            {
                "conversation_id": conv_id,
                "merchant_id": trg.get("merchant_id"),
                "customer_id": trg.get("customer_id"),
                "send_as": composed["send_as"],
                "trigger_id": trg_id,
                "template_name": _template_name(trigger, composed["send_as"]),
                "template_params": [owner or merchant.get("identity", {}).get("name", ""), composed["body"][:80]],
                "body": composed["body"],
                "cta": composed["cta"],
                "suppression_key": sk,
                "rationale": composed["rationale"],
            }
        )

    return {"actions": actions}


class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str
    message: str
    received_at: str
    turn_number: int


@app.post("/v1/reply")
async def reply(body: ReplyBody):
    state = conversations.get(body.conversation_id)
    if not state:
        state = ConversationState(
            conversation_id=body.conversation_id,
            merchant_id=body.merchant_id,
            customer_id=body.customer_id,
        )
        conversations[body.conversation_id] = state

    result = respond(state, body.message)

    if result.get("action") == "send":
        body_text = result.get("body", "")
        if body_text in state.sent_bodies:
            result = {
                "action": "end",
                "rationale": "Avoiding verbatim repetition in conversation",
            }
        else:
            state.last_bot_body = body_text
            state.sent_bodies.append(body_text)

    if result.get("action") == "end":
        prefix = f"conv_{body.merchant_id}_"
        active_conversations.difference_update({k for k in active_conversations if k.startswith(prefix)})

    return result


@app.post("/v1/teardown")
async def teardown():
    contexts.clear()
    conversations.clear()
    suppression_sent.clear()
    active_conversations.clear()
    reset_merchant_tracking()
    return {"status": "wiped"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "bot:app",
        host="0.0.0.0",
        port=_server_port(),
    )
