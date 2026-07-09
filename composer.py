from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from env_utils import load_env_file
from context_utils import (
    active_offers,
    business_name,
    city,
    customer_name,
    digest_item,
    first_active_offer,
    format_pct,
    locality,
    months_since,
    owner_name,
    peer_ctr,
    peer_rating,
    peer_reviews,
    performance,
    salutation,
    send_as,
    signals,
    strip_taboos,
    suppression_key,
    uses_hindi,
)

load_env_file()

Handler = Callable[[dict, dict, dict, dict | None], dict]


def compose(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: dict | None = None,
) -> dict:
    """Compose a WhatsApp message from the 4 Vera contexts."""
    if os.getenv("COMPOSER_MODE", "template").lower() == "llm":
        try:
            from llm_client import compose_with_llm

            return compose_with_llm(category, merchant, trigger, customer)
        except Exception:
            pass

    kind = trigger.get("kind", "unknown")
    handler = HANDLERS.get(kind, _compose_generic)
    result = handler(category, merchant, trigger, customer)
    return _finalize(result, category, merchant, trigger, customer)


def _base(
    body: str,
    cta: str,
    rationale: str,
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: dict | None,
) -> dict:
    return {
        "body": strip_taboos(body.strip(), category),
        "cta": cta,
        "send_as": send_as(trigger, customer),
        "suppression_key": suppression_key(trigger),
        "rationale": rationale,
    }


def _finalize(result: dict, category: dict, merchant: dict, trigger: dict, customer: dict | None) -> dict:
    body = result.get("body", "").strip()
    if not body:
        result = _compose_generic(category, merchant, trigger, customer)
        body = result["body"]
    if len(body) > 900:
        body = body[:897].rsplit(" ", 1)[0] + "..."
        result["body"] = body
    result.setdefault("send_as", send_as(trigger, customer))
    result.setdefault("suppression_key", suppression_key(trigger))
    result.setdefault("cta", "open_ended")
    result.setdefault("rationale", f"Composed for trigger kind={trigger.get('kind')}")
    return result





def _compose_research_digest(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    item = digest_item(category, payload.get("top_item_id"))
    greet = salutation(merchant, category)
    hi = uses_hindi(merchant, customer)

    if item:
        title = item.get("title", "")
        source = item.get("source", "")
        trial_n = item.get("trial_n")
        segment = item.get("patient_segment") or item.get("segment", "")
        actionable = item.get("actionable", "")
        detail = f"{trial_n:,}-patient trial" if trial_n else title
        seg_note = f" — relevant to your {segment.replace('_', ' ')} cohort" if segment else ""
        if hi:
            body = (
                f"{greet}, is hafte ki research digest mein ek item aapke liye useful lag raha hai{seg_note}. "
                f"{detail}. {actionable or 'Worth a 2-min read'}. "
                f"Main abstract pull karun + patient-ed WhatsApp draft bana doon? — {source}"
            )
        else:
            body = (
                f"{greet}, this week's research digest has one item worth your time{seg_note}. "
                f"{detail}. {actionable or 'Worth a 2-min read'}. "
                f"Want me to pull the abstract + draft a patient-ed WhatsApp you can share? — {source}"
            )
        rationale = f"Research digest item {item.get('id')} with source citation and low-friction CTA"
    else:
        body = (
            f"{greet}, fresh {category.get('slug', 'category')} research landed this week. "
            f"Want me to pull the top 2 items relevant to {locality(merchant) or city(merchant)}?"
        )
        rationale = "Research digest trigger without resolved item — curiosity hook"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_regulation_change(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    item = digest_item(category, payload.get("top_item_id"))
    greet = salutation(merchant, category)
    deadline = payload.get("deadline_iso", "")
    deadline_fmt = deadline[:10] if deadline else "soon"

    if item:
        title = item.get("title", "")
        source = item.get("source", "")
        actionable = item.get("actionable", "")
        body = (
            f"{greet}, compliance heads-up: {title}. Deadline {deadline_fmt}. "
            f"{actionable} Want me to draft an SOP checklist for your clinic? — {source}"
        )
        rationale = f"Regulation change with deadline {deadline_fmt} and actionable compliance step"
    else:
        body = (
            f"{greet}, a new {category.get('slug', '')} regulation takes effect {deadline_fmt}. "
            f"Want me to pull the summary + what to audit before the deadline?"
        )
        rationale = "Regulation change trigger with deadline anchor"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_competitor_opened(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    hi = uses_hindi(merchant, customer)

    if payload.get("placeholder"):
        trends = category.get("trend_signals", [])
        trend_line = trends[0].get("query", "local competition") if trends else "new listings nearby"
        if hi:
            body = (
                f"{greet}, {locality(merchant) or city(merchant)} mein nayi activity — "
                f"'{trend_line}' searches badh rahi hain. Aapke GBP vs area median compare karun?"
            )
        else:
            body = (
                f"{greet}, new activity near you in {locality(merchant) or city(merchant)} — "
                f"'{trend_line}' searches are rising. Want a side-by-side GBP comparison?"
            )
        rationale = "Competitor signal with category trend anchor (no fabricated competitor name)"
        return _base(body, "open_ended", rationale, category, merchant, trigger, customer)

    comp = payload.get("competitor_name", "A new competitor")
    dist = payload.get("distance_km", "?")
    their_offer = payload.get("their_offer", "")
    opened = payload.get("opened_date", "")[:10]
    my_offer = first_active_offer(merchant, category)

    offer_line = f" They're running {their_offer}." if their_offer else ""
    counter = f" Your active offer: {my_offer}." if my_offer else ""
    if hi:
        body = (
            f"{greet}, {locality(merchant)} mein ek naya listing live hua — {comp}, {dist} km door"
            f"{offer_line} Opened {opened}.{counter} "
            f"Unka GBP profile dekhna chahenge? Main side-by-side diff bhej sakti hoon."
        )
    else:
        body = (
            f"{greet}, a new listing went live near you — {comp}, {dist} km away in {locality(merchant)}"
            f"{offer_line} Opened {opened}.{counter} "
            f"Want to see their GBP profile side-by-side with yours?"
        )
    rationale = f"Competitor opened {comp} at {dist}km — curiosity + loss aversion framing"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_perf_dip(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    metric = payload.get("metric", "calls")
    delta = float(payload.get("delta_pct", -0.2))
    baseline = payload.get("vs_baseline", performance(merchant).get(metric, "?"))
    perf = performance(merchant)
    current = perf.get(metric, baseline)
    hi = uses_hindi(merchant, customer)

    if hi:
        body = (
            f"{greet}, aapke dashboard pe {metric} pichle 7 din mein {format_pct(delta)} hai "
            f"({baseline} se {current}). {locality(merchant)} mein peer median "
            f"{peer_ctr(category)*100:.1f}% CTR hai. Main 2 quick fixes suggest karun?"
        )
    else:
        body = (
            f"{greet}, your dashboard shows {metric} down {format_pct(delta)} this week "
            f"({baseline} → {current}). Peers in {locality(merchant) or city(merchant)} avg "
            f"{peer_ctr(category)*100:.1f}% CTR. Want me to suggest 2 quick fixes?"
        )
    rationale = f"Perf dip on {metric} ({format_pct(delta)}) with peer benchmark anchor"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_perf_spike(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    metric = payload.get("metric", "views")
    delta = float(payload.get("delta_pct", payload.get("views_pct", 0.2)))
    perf = performance(merchant)
    current = perf.get(metric, "?")
    hi = uses_hindi(merchant, customer)

    if hi:
        body = (
            f"{greet}, achhi khabar — {metric} kal {format_pct(delta)} badha ({current} total 30d). "
            f"Yeh momentum capitalize karne ke liye main ek Google Post draft kar doon?"
        )
    else:
        body = (
            f"{greet}, good news — {metric} spiked {format_pct(delta)} yesterday "
            f"({current} in your 30d window). Want me to draft a Google Post to ride this momentum?"
        )
    rationale = f"Perf spike on {metric} ({format_pct(delta)}) — reciprocity + low-friction next step"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_milestone_reached(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    metric = payload.get("metric", "reviews").replace("_", " ")
    value = (
        payload.get("value_now")
        or payload.get("milestone_value")
        or payload.get("value")
        or payload.get("count")
        or peer_reviews(category)
    )
    hi = uses_hindi(merchant, customer)

    if hi:
        body = (
            f"{greet}, milestone — aapne {value} {metric} cross kar liye! "
            f"Is moment ko ek thank-you Google Post se celebrate karein? Main draft ready kar deti hoon."
        )
    else:
        body = (
            f"{greet}, milestone hit — you just crossed {value} {metric}! "
            f"Want me to draft a thank-you Google Post to celebrate with your customers?"
        )
    rationale = f"Milestone {metric}={value} — social proof + celebration CTA"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_curious_ask_due(category, merchant, trigger, customer) -> dict:
    greet = salutation(merchant, category)
    slug = category.get("slug", "")
    hi = uses_hindi(merchant, customer)
    asks = {
        "dentists": "iss hafte sabse zyada kaun sa treatment puchha ja raha hai?",
        "salons": "iss hafte sabse zyada demand kis service ki rahi?",
        "restaurants": "iss hafte kaun sa dish sabse zyada order hua?",
        "gyms": "iss hafte naye members kis program ke liye puchh rahe hain?",
        "pharmacies": "iss hafte sabse zyada kya stock-out hua?",
    }
    ask = asks.get(slug, "what's been your busiest service this week?")
    if hi:
        body = f"{greet}, quick question — {ask} Bas ek line reply karein, main aapke liye trend report update kar dungi."
    else:
        body = f"{greet}, quick question — {ask} One-line reply is enough; I'll update your trend report."
    rationale = "Curious ask — merchant input drives engagement (#7 compulsion lever)"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_dormant_with_vera(category, merchant, trigger, customer) -> dict:
    greet = salutation(merchant, category)
    perf = performance(merchant)
    views = perf.get("views", "?")
    sig = signals(merchant)
    stale = next((s for s in sig if s.startswith("stale_posts")), None)
    hi = uses_hindi(merchant, customer)

    hook = ""
    if stale:
        hook = f" Aapke Google posts {stale.split(':')[-1]} purane hain."
    elif views != "?":
        hook = f" Aapke profile pe pichle 30 din mein {views} views aaye."

    if hi:
        body = (
            f"{greet}, kaafi din ho gaye — ek quick update.{hook} "
            f"Kya main 2-min audit bhej doon jo abhi fix ho sakta hai?"
        )
    else:
        body = (
            f"{greet}, it's been a while — quick check-in.{hook} "
            f"Want a 2-min audit of what's fixable on your profile right now?"
        )
    rationale = "Dormant merchant re-engagement with verifiable profile hook"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_festival_upcoming(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    hi = uses_hindi(merchant, customer)
    offer = first_active_offer(merchant, category)
    offer_note = f" Aapka active offer: {offer}." if offer else ""

    if payload.get("placeholder") or not payload.get("festival"):
        beats = category.get("seasonal_beats", [])
        beat = beats[0].get("note", "seasonal peak") if beats else "seasonal peak"
        if hi:
            body = (
                f"{greet}, seasonal heads-up — {beat}.{offer_note} "
                f"Is window ke liye Google Post + WhatsApp broadcast draft kar doon? Bas YES bolein."
            )
        else:
            body = (
                f"{greet}, seasonal heads-up — {beat}.{offer_note} "
                f"Want me to draft a Google Post + WhatsApp broadcast for this window? Reply YES."
            )
        rationale = f"Seasonal beat from category context: {beat[:60]}"
        return _base(body, "yes_stop", rationale, category, merchant, trigger, customer)

    festival = payload.get("festival", "the upcoming festival")
    days = payload.get("days_until", "soon")
    if hi:
        body = (
            f"{greet}, {festival} {days} din mein hai.{offer_note} "
            f"Festival Google Post + WhatsApp broadcast draft kar doon? Bas YES bolein."
        )
    else:
        body = (
            f"{greet}, {festival} is {days} days away.{offer_note} "
            f"Want me to draft a festival Google Post + WhatsApp broadcast? Reply YES."
        )
    rationale = f"Festival {festival} in {days} days — seasonal timing + binary CTA"
    return _base(body, "yes_stop", rationale, category, merchant, trigger, customer)


def _compose_gbp_unverified(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    uplift = int(float(payload.get("estimated_uplift_pct", 0.3)) * 100)
    path = payload.get("verification_path", "postcard or phone")
    hi = uses_hindi(merchant, customer)

    if hi:
        body = (
            f"{greet}, aapka Google profile abhi unverified hai — verified listings ko avg {uplift}% zyada clicks milte hain. "
            f"Verification via {path}. Main step-by-step guide bhej doon?"
        )
    else:
        body = (
            f"{greet}, your Google profile is still unverified — verified listings see ~{uplift}% more clicks on average. "
            f"Verification via {path}. Want me to send the step-by-step guide?"
        )
    rationale = f"Unverified GBP with {uplift}% uplift stat and clear verification path"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_active_planning_intent(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    topic = payload.get("intent_topic", "your plan").replace("_", " ")
    last_msg = payload.get("merchant_last_message", "")
    offer = first_active_offer(merchant, category)
    hi = uses_hindi(merchant, customer)

    msg_hi = f': "{last_msg[:60]}..."' if last_msg else ""
    msg_en = f' — you asked: "{last_msg[:80]}"' if last_msg else ""
    offer_hi = f"Reference offer: {offer}. " if offer else ""
    offer_en = f"Using your offer {offer} as anchor. " if offer else ""

    if hi:
        body = (
            f"{greet}, aapne {topic} ke baare mein pucha tha{msg_hi}. "
            f"Main ek 3-point draft ready kar diya hai — pricing, inclusions, aur launch timeline. "
            f"{offer_hi}Bhej doon?"
        )
    else:
        body = (
            f"{greet}, following up on {topic}{msg_en}. "
            f"I've drafted a 3-point plan: pricing, inclusions, and launch timeline. "
            f"{offer_en}Want me to send it?"
        )
    rationale = f"Action mode for planning intent on {topic} — honors merchant's explicit ask"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_cde_opportunity(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    item = digest_item(category, payload.get("digest_item_id"))
    greet = salutation(merchant, category)
    credits = payload.get("credits", item.get("credits") if item else 2)

    if item:
        title = item.get("title", "")
        source = item.get("source", "")
        date = (item.get("date") or "")[:10]
        summary = item.get("summary", "")
        body = (
            f"{greet}, CDE alert: {title} — {date}. {credits} credits. "
            f"{summary[:120]}{'...' if len(summary) > 120 else ''} "
            f"Register link bhej doon? — {source}"
        )
    else:
        body = (
            f"{greet}, a CDE webinar with {credits} credits is coming up in your specialty. "
            f"Want the registration link?"
        )
    rationale = f"CDE opportunity with {credits} credits and source citation"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_summer_demand_shift(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    product = payload.get("product", payload.get("category_shift", "seasonal items"))
    delta = payload.get("demand_delta_pct", payload.get("delta_pct", 0.25))
    hi = uses_hindi(merchant, customer)

    if hi:
        body = (
            f"{greet}, {city(merchant)} mein {product} ki demand {format_pct(float(delta))} badh rahi hai is summer. "
            f"Aapke listing pe yeh highlight karne ke liye Google Post draft kar doon?"
        )
    else:
        body = (
            f"{greet}, demand for {product} is up {format_pct(float(delta))} this summer in {city(merchant)}. "
            f"Want me to draft a Google Post highlighting your relevant stock/services?"
        )
    rationale = f"Seasonal demand shift on {product} ({format_pct(float(delta))})"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_ipl_match_today(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    match = payload.get("match", "today's match")
    venue = payload.get("venue", city(merchant))
    match_time = payload.get("match_time_iso", "")[:16].replace("T", " ")
    hi = uses_hindi(merchant, customer)

    if hi:
        body = (
            f"{greet}, aaj {match} {venue} pe {match_time} baje — footfall badhega. "
            f"Match-day combo offer + Google Post draft kar doon?"
        )
    else:
        body = (
            f"{greet}, {match} at {venue} today ({match_time}) — expect higher footfall. "
            f"Want me to draft a match-day combo offer + Google Post?"
        )
    rationale = f"IPL match {match} — timely local event offer"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_local_event(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    event = payload.get("event", payload.get("match", "a local event"))
    date = payload.get("date", "")[:10]
    hi = uses_hindi(merchant, customer)

    if hi:
        body = (
            f"{greet}, {event} {date} ko hai — {locality(merchant) or city(merchant)} mein footfall badhega. "
            f"Match-day offer + Google Post draft kar doon?"
        )
    else:
        body = (
            f"{greet}, {event} on {date} — expect higher footfall in {locality(merchant) or city(merchant)}. "
            f"Want me to draft a match-day offer + Google Post?"
        )
    rationale = f"Local event {event} — timely offer opportunity"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_renewal_due(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    days = payload.get("days_remaining", _safe_get(merchant, "subscription", "days_remaining", default="?"))
    plan = payload.get("plan", _safe_get(merchant, "subscription", "plan", default="Pro"))
    amount = payload.get("renewal_amount", "")

    amount_note = f" Renewal: ₹{amount:,}." if amount else ""
    body = (
        f"{greet}, your {plan} plan renews in {days} days.{amount_note} "
        f"Want me to send the renewal link, or need to adjust your plan first?"
    )
    rationale = f"Renewal due in {days} days — functional nudge with clear action"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_review_theme_emerged(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    theme = payload.get("theme", "service quality")
    count = payload.get("occurrences", payload.get("count", 3))
    hi = uses_hindi(merchant, customer)

    if hi:
        body = (
            f"{greet}, pichle hafte {count} reviews mein '{theme}' mention hua — pattern dikh raha hai. "
            f"Main ek response template + fix checklist bhej doon?"
        )
    else:
        body = (
            f"{greet}, {count} reviews this week mention '{theme}' — a pattern is emerging. "
            f"Want me to send a response template + fix checklist?"
        )
    rationale = f"Review theme '{theme}' x{count} — actionable reputation signal"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


# ---------------------------------------------------------------------------
# Customer-facing handlers
# ---------------------------------------------------------------------------


def _compose_recall_due(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    name = customer_name(customer)
    biz = business_name(merchant)
    offer = first_active_offer(merchant, category)
    slots = payload.get("available_slots", [])
    last_visit = payload.get("last_service_date", _safe_get(customer, "relationship", "last_visit"))
    months = months_since(last_visit)
    hi = uses_hindi(merchant, customer)

    slot_text = ""
    if len(slots) >= 2:
        slot_text = f" Reply 1 for {slots[0].get('label')}, 2 for {slots[1].get('label')}."
    elif len(slots) == 1:
        slot_text = f" Slot ready: {slots[0].get('label')}."
    else:
        slot_text = " Reply with a time that works."

    time_note = f"It's been {months} months since your last visit — " if months else ""
    offer_note = f"{offer}. " if offer else ""

    if hi:
        body = (
            f"Hi {name}, {biz} se 🦷 {time_note}aapki cleaning recall due hai. "
            f"{offer_note}Apke liye 2 slots ready hain:{slot_text}"
        )
    else:
        body = (
            f"Hi {name}, {biz} here. {time_note}Your recall appointment is due. "
            f"{offer_note}{slot_text.strip()}"
        )
    rationale = f"Recall due for {name} — slots + service+price anchor"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_appointment_tomorrow(category, merchant, trigger, customer) -> dict:
    name = customer_name(customer)
    biz = business_name(merchant)
    hi = uses_hindi(merchant, customer)

    if hi:
        body = (
            f"Hi {name}, {biz} se — reminder: aapki appointment kal hai. "
            f"Confirm karne ke liye YES reply karein, reschedule ke liye apna preferred time bata dein."
        )
    else:
        body = (
            f"Hi {name}, {biz} here — reminder: your appointment is tomorrow. "
            f"Reply YES to confirm, or send your preferred time to reschedule."
        )
    rationale = f"Appointment reminder for {name} — low-friction confirm/reschedule"
    return _base(body, "yes_stop", rationale, category, merchant, trigger, customer)


def _compose_chronic_refill(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    name = customer_name(customer)
    biz = business_name(merchant)
    molecules = payload.get("molecule_list", [])
    med = payload.get("medication", payload.get("product", ""))
    if not med and molecules:
        med = ", ".join(molecules[:2])
    if not med and customer:
        services = _safe_get(customer, "relationship", "services_received", default=[]) or []
        if services:
            med = f"{services[-1]} follow-up"
    if not med:
        med = "prescription refill"
    due = payload.get("stock_runs_out_iso", payload.get("refill_due_date", payload.get("due_date", "")))[:10]
    delivery = payload.get("delivery_address_saved", False)
    hi = uses_hindi(merchant, customer)

    due_note = f" Stock runs out by {due}." if due else ""
    delivery_note = " Saved address pe delivery." if delivery else ""
    if hi:
        body = (
            f"Hi {name}, {biz} se — aapki {med} ki refill due hai.{due_note}{delivery_note} "
            f"Home delivery chahiye? YES reply karein."
        )
    else:
        body = (
            f"Hi {name}, {biz} here — your {med} refill is due.{due_note}{delivery_note} "
            f"Need home delivery? Reply YES."
        )
    rationale = f"Chronic refill reminder for {med} — convenience CTA"
    return _base(body, "yes_stop", rationale, category, merchant, trigger, customer)


def _compose_category_seasonal(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    greet = salutation(merchant, category)
    trends = payload.get("trends", [])
    season = payload.get("season", "this season").replace("_", " ")
    hi = uses_hindi(merchant, customer)

    trend_line = ", ".join(t.replace("_", " ") for t in trends[:3]) if trends else "seasonal demand shifts"
    if hi:
        body = (
            f"{greet}, {season} mein {city(merchant)} mein demand shift: {trend_line}. "
            f"Aapke listing pe in items highlight karne ke liye Google Post draft kar doon?"
        )
    else:
        body = (
            f"{greet}, {season} demand shifts in {city(merchant)}: {trend_line}. "
            f"Want me to draft a Google Post highlighting your relevant stock?"
        )
    rationale = f"Category seasonal trends: {trend_line[:80]}"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_customer_lapsed_hard(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    name = customer_name(customer)
    biz = business_name(merchant)
    days = payload.get("days_since_last_visit", "?")
    focus = payload.get("previous_focus", "").replace("_", " ")
    offer = first_active_offer(merchant, category)
    hi = uses_hindi(merchant, customer)

    focus_note = f" Aapka last focus {focus} tha." if focus else ""
    offer_note = f" Comeback offer: {offer}." if offer else ""
    if hi:
        body = (
            f"Hi {name}, {biz} se — {days} din ho gaye aapke last visit ko.{focus_note}{offer_note} "
            f"Wapas aane ke liye YES reply karein, main slot hold kar deta hoon."
        )
    else:
        body = (
            f"Hi {name}, {biz} here — it's been {days} days since your last visit.{focus_note}{offer_note} "
            f"Reply YES to come back and I'll hold a slot for you."
        )
    rationale = f"Winback for {name} after {days} days — loss aversion + offer"
    return _base(body, "yes_stop", rationale, category, merchant, trigger, customer)


def _compose_customer_lapsed_soft(category, merchant, trigger, customer) -> dict:
    name = customer_name(customer)
    biz = business_name(merchant)
    last_visit = _safe_get(customer, "relationship", "last_visit")
    months = months_since(last_visit)
    offer = first_active_offer(merchant, category)
    hi = uses_hindi(merchant, customer)

    time_note = f"{months} months" if months else "a while"
    offer_note = f" {offer} available." if offer else ""
    if hi:
        body = (
            f"Hi {name}, {biz} se — {time_note} ho gaye aapki last visit ko.{offer_note} "
            f"Ek follow-up slot book karein? Apna preferred time bata dein."
        )
    else:
        body = (
            f"Hi {name}, {biz} here — it's been {time_note} since your last visit.{offer_note} "
            f"Want to book a follow-up? Send your preferred time."
        )
    rationale = f"Soft lapse winback for {name} — gentle re-engagement"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _compose_generic(category, merchant, trigger, customer) -> dict:
    payload = trigger.get("payload", {})
    kind = trigger.get("kind", "update")
    greet = salutation(merchant, category)
    hi = uses_hindi(merchant, customer)

    if trigger.get("scope") == "customer" and customer:
        return _compose_customer_lapsed_soft(category, merchant, trigger, customer)

    perf = performance(merchant)
    views = perf.get("views")
    topic = payload.get("metric_or_topic", kind.replace("_", " "))
    offer = first_active_offer(merchant, category)

    if hi:
        body = (
            f"{greet}, aapke account pe ek update hai — {topic}. "
            f"{'30d views: ' + str(views) + '. ' if views else ''}"
            f"{'Active offer: ' + offer + '. ' if offer else ''}"
            f"Details bhej doon?"
        )
    else:
        body = (
            f"{greet}, an update on your account — {topic}. "
            f"{'30d views: ' + str(views) + '. ' if views else ''}"
            f"{'Active offer: ' + offer + '. ' if offer else ''}"
            f"Want me to send the details?"
        )
    rationale = f"Generic handler for kind={kind} using available merchant signals"
    return _base(body, "open_ended", rationale, category, merchant, trigger, customer)


def _safe_get(obj, *keys, default=None):
    cur = obj or {}
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


HANDLERS: dict[str, Handler] = {
    "research_digest": _compose_research_digest,
    "regulation_change": _compose_regulation_change,
    "competitor_opened": _compose_competitor_opened,
    "perf_dip": _compose_perf_dip,
    "perf_spike": _compose_perf_spike,
    "milestone_reached": _compose_milestone_reached,
    "curious_ask_due": _compose_curious_ask_due,
    "dormant_with_vera": _compose_dormant_with_vera,
    "festival_upcoming": _compose_festival_upcoming,
    "gbp_unverified": _compose_gbp_unverified,
    "active_planning_intent": _compose_active_planning_intent,
    "cde_opportunity": _compose_cde_opportunity,
    "summer_demand_shift": _compose_summer_demand_shift,
    "ipl_match_today": _compose_ipl_match_today,
    "ipl_match": _compose_ipl_match_today,
    "local_event": _compose_local_event,
    "renewal_due": _compose_renewal_due,
    "review_theme_emerged": _compose_review_theme_emerged,
    "recall_due": _compose_recall_due,
    "appointment_tomorrow": _compose_appointment_tomorrow,
    "chronic_refill_due": _compose_chronic_refill,
    "chronic_refill": _compose_chronic_refill,
    "category_seasonal": _compose_category_seasonal,
    "customer_lapsed_hard": _compose_customer_lapsed_hard,
    "customer_lapsed_soft": _compose_customer_lapsed_soft,
}
