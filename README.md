# Vera Challenge Bot

AI merchant assistant developed for the magicpin AI Challenge.

The bot generates contextual WhatsApp conversations using the four-context framework:

- Category context
- Merchant context
- Customer context
- Trigger context

The bot exposes the required HTTP APIs consumed by the magicpin Judge Harness.

---

# Approach

## Trigger Routed Context Composer

The bot follows a deterministic composition approach.

For every active trigger:

1. Fetch relevant trigger context
2. Identify merchant/customer context
3. Retrieve category information
4. Extract only verified facts
5. Generate a contextual Vera message

## Design Principles

- Deterministic output by default
- No hallucinated information
- Low latency responses
- Context-aware message generation
- Stateful conversation handling

---

# Architecture

```text
          Magicpin Judge Harness

                   |
                   |
             HTTP JSON API

                   |
                   v

            FastAPI Application

    +-------------------------------+
    |                               |
    v                               v

Context Store                 Conversation Store

(category, merchant,          Multi-turn history
customer, trigger)

          |
          v

     Composer Engine

          |
          v

      Vera Messages
```

---

# Implemented APIs

## POST `/v1/context`

Receives context updates from the judge.

Supported contexts:

- category
- merchant
- customer
- trigger

### Features

- Version-based updates
- Duplicate context handling
- Persistent in-memory context storage

---

## POST `/v1/tick`

Called periodically by the judge.

The bot:

- Checks available triggers
- Finds related contexts
- Decides whether to send a proactive message
- Returns generated actions

Example:

```json
{
  "actions": []
}
```

---

## POST `/v1/reply`

Handles merchant/customer replies.

Supports:

- Follow-up conversations
- Acceptance handling
- Rejection handling
- Graceful exits
- Wait decisions

---

## GET `/v1/healthz`

Health monitoring endpoint.

Returns:

- Server status
- Uptime
- Loaded context counts

Example:

```json
{
  "status": "ok",
  "uptime_seconds": 100,
  "contexts_loaded": {
    "category": 5,
    "merchant": 50,
    "customer": 200,
    "trigger": 0
  }
}
```

---

## GET `/v1/metadata`

Returns bot identity and implementation details.

---

# Conversation Handling

Implemented handlers for:

## Auto Reply Detection

Detects repeated WhatsApp automated responses and avoids unnecessary continuation.

## Merchant Commitment

When the merchant shows positive intent (e.g., "Okay let's do it"), the bot proceeds toward the next action instead of asking redundant questions.

## Negative Responses

Handles:

- Rejection
- Hostility
- Irrelevant queries

with polite exits.

---

# Testing

The bot was tested using the provided:

```bash
judge_simulator.py
```

Run locally:

```bash
uvicorn bot:app --host 0.0.0.0 --port 8080
```

Run simulator:

```bash
python judge_simulator.py
```

Testing covers:

- Context ingestion
- Health checks
- Trigger processing
- Message generation
- Conversation replies
- API contract validation

---

# Deployment

The bot is deployed as a public HTTPS FastAPI service.

### Base URL

```
https://magicpin-ai-challenge-67jm.onrender.com
```

Judge endpoints:

```
/v1/context
/v1/tick
/v1/reply
/v1/healthz
/v1/metadata
```

---

# Tradeoffs

## Advantages

- Fast deterministic responses
- Reduced hallucination risk
- Easy debugging
- Stable evaluation behavior

## Limitations

- Less variation compared to fully LLM-generated responses
- Requires maintaining templates and conversation handlers

---

# Future Improvements

- Hybrid LLM + deterministic generation
- Improved retrieval over context libraries
- More category-specific conversation strategies
- Long-term conversation memory

---

# Tech Stack

- Python
- FastAPI
- Pydantic
- JSON Context Storage
- Rule-based Composer Engine
- Conversation State Management
