# Vera Challenge Bot

AI merchant assistant for the magicpin AI Challenge — composes contextual WhatsApp messages from the 4-context framework (category, merchant, trigger, customer).

## Approach

- **Trigger-routed template composer** — each `trigger.kind` has a dedicated handler that extracts verifiable facts from contexts (numbers, dates, citations, peer stats, offers).
- **Deterministic by default** — no LLM required for submission; same inputs always produce the same output.
- **Optional LLM mode** — set `COMPOSER_MODE=llm` with `GEMINI_API_KEY` or `OPENAI_API_KEY` for LLM-backed composition.
- **Multi-turn handlers** — auto-reply detection (exit after 2 canned replies), immediate action on commitment, graceful exit on hostility.

## Tradeoffs

- Templates score well on specificity and avoid hallucination, but are less varied than a frontier LLM.
- Placeholder trigger payloads fall back to merchant/customer context rather than inventing missing data.
- Hindi-English code-mix is applied when merchant languages include `hi` or customer pref is `hi-en mix`.

## What would help most

- Real-time booking slot data for appointment triggers
- Richer conversation history tags for smarter re-engagement
- Category-specific curious-ask question banks per locality

## Run locally

```bash
pip install -r requirements.txt
python generate_submission.py          # creates submission.jsonl
uvicorn bot:app --host 0.0.0.0 --port 8080
```

## Files

| File | Purpose |
|---|---|
| `bot.py` | FastAPI server + `compose()` export |
| `composer.py` | Core message composition engine |
| `conversation_handlers.py` | Multi-turn reply routing |
| `context_utils.py` | Context extraction helpers |
| `generate_submission.py` | Batch-generate 30 test messages |
| `submission.jsonl` | Required 30-line submission |

## Optional LLM mode

```bash
set COMPOSER_MODE=llm
set GEMINI_API_KEY=your-key 
python generate_submission.py
```
