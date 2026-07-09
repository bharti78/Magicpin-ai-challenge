# Vera Challenge Bot

AI merchant assistant for the magicpin AI Challenge — consumes category, merchant, trigger, and customer contexts to compose contextual WhatsApp messages.

## Approach

* **Trigger-routed template composer** — each `trigger.kind` has a dedicated handler that extracts verifiable facts from available contexts (numbers, dates, citations, peer stats, offers).
* **Deterministic by default** — no LLM required for submission; identical inputs always produce consistent outputs.
* **Optional LLM mode** — supports LLM-backed composition using `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `GROQ_API_KEY` when `COMPOSER_MODE=llm`.
* **Multi-turn handlers** — includes auto-reply detection (exit after repeated canned replies), immediate action after merchant commitment, and graceful handling of hostile responses.

## Tradeoffs

* Templates score well on specificity and avoid hallucination, but provide less variation compared to a fully generative LLM approach.
* Missing trigger payload data falls back to available merchant/category/customer context instead of inventing information.
* Hindi-English code-mix is applied when merchant language preferences include `hi` or customer preference indicates `hi-en mix`.

## What Would Help Most

* Real-time booking slot availability for appointment-related triggers.
* Richer conversation history signals for smarter re-engagement.
* Category-specific curiosity-driven question banks based on locality and merchant behavior.

## Deployment

The bot is deployed as a FastAPI service and exposes the following endpoints:

| Endpoint       | Method | Purpose                                               |
| -------------- | ------ | ----------------------------------------------------- |
| `/v1/healthz`  | GET    | Health check                                          |
| `/v1/metadata` | GET    | Bot metadata                                          |
| `/v1/context`  | POST   | Push category, merchant, trigger, or customer context |
| `/v1/tick`     | POST   | Process available triggers                            |
| `/v1/reply`    | POST   | Handle merchant conversations                         |
| `/v1/teardown` | POST   | Reset in-memory state                                 |

## Run Locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Generate submission messages:

```bash
python generate_submission.py
```

Run the FastAPI server:

```bash
uvicorn bot:app --host 0.0.0.0 --port 8080
```

## Files

| File                       | Purpose                                       |
| -------------------------- | --------------------------------------------- |
| `bot.py`                   | FastAPI server + `compose()` export           |
| `composer.py`              | Core trigger-based message composition engine |
| `conversation_handlers.py` | Multi-turn conversation routing               |
| `context_utils.py`         | Context extraction and helper utilities       |
| `generate_submission.py`   | Generates evaluated test messages             |
| `submission.jsonl`         | Generated 30-line submission output           |

## Optional LLM Mode

Enable LLM-backed composition:

### Windows PowerShell

```powershell
$env:COMPOSER_MODE="llm"
$env:GEMINI_API_KEY="your-key"
```

or:

```powershell
$env:COMPOSER_MODE="llm"
$env:OPENAI_API_KEY="your-key"
```

or:

```powershell
$env:COMPOSER_MODE="llm"
$env:GROQ_API_KEY="your-key"
```

Then run:

```bash
python generate_submission.py
```

## Design Notes

The bot keeps the core composition deterministic to ensure:

* reproducible outputs,
* no hallucinated merchant claims,
* reliable multi-turn behavior,
* predictable evaluation results.

The architecture can be extended with external storage and richer real-time signals for production-scale deployments.
