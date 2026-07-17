# Vera Challenge Bot

AI WhatsApp assistant for the magicpin AI Challenge.

Vera generates context-aware merchant/customer conversations from the four-context framework:

- Category context
- Merchant context
- Customer context
- Trigger context

The service exposes the HTTP API expected by the judge harness and keeps runtime state in memory, as allowed by the challenge.

---

# Approach

## Hybrid Vera Bot

The bot uses a hybrid architecture:

- Deterministic trigger-specific composer for stable first messages
- Optional LLM-backed composer/reply engine for richer context-aware conversations
- Hard guardrails for stop requests, auto-replies, repeated messages, and API failures
- Deterministic fallback whenever the LLM is unavailable or returns invalid output

This gives the bot the scoring potential of an LLM system while keeping it robust under judge timeouts and edge cases.

## Message Principles

- Use only verified facts from provided context
- Never invent offers, competitors, numbers, or claims
- Match category tone:
  - Dentists/doctors: clinical and peer-to-peer
  - Salons: warm and practical
  - Restaurants: operator-to-operator
  - Gyms: coaching-oriented
  - Pharmacies: precise and trustworthy
- Keep one CTA at the end
- Avoid repeated message bodies within a conversation
- End politely on stop, hostility, or clear disinterest
- Handle WhatsApp Business auto-replies without looping

---

# Architecture

```text
Magicpin Judge Harness
        |
        v
FastAPI HTTP API
        |
        +--> In-memory context store
        |       (category, merchant, customer, trigger)
        |
        +--> Tick composer
        |       deterministic handlers + optional LLM
        |
        +--> Reply handler
                guardrails + optional LLM + fallback
```

Core files:

- `bot.py` - FastAPI server and API contract
- `composer.py` - deterministic trigger-routed first-message composer
- `conversation_handlers.py` - multi-turn reply state and guardrails
- `llm_client.py` - optional Groq/Gemini/OpenAI LLM integration
- `judge_simulator.py` - local judge simulation

---

# Implemented APIs

## `GET /v1/healthz`

Returns service health, uptime, and loaded context counts.

## `GET /v1/metadata`

Returns team identity, active model, approach, and version metadata.

## `POST /v1/context`

Stores category, merchant, customer, and trigger context.

Features:

- Version-aware updates
- Duplicate-version acceptance
- Invalid-scope rejection
- In-memory storage

## `POST /v1/tick`

Called by the judge to ask whether Vera wants to send proactive messages.

Features:

- Trigger prioritization by urgency
- Suppression-key tracking
- Active-conversation tracking
- Maximum 20 actions per tick
- 24-second time budget to avoid judge timeout
- Partial action return if time budget is close

## `POST /v1/reply`

Handles merchant/customer replies.

Features:

- Commitment transition: moves to action mode on “yes”, “ok”, “let’s do it”, “what next”
- Auto-reply detection: sends one human-check nudge, then exits on repeat
- Hostile/stop handling: ends immediately and politely
- Wait handling when merchant asks for time
- No verbatim repeated Vera messages
- Optional LLM reply generation with deterministic fallback

---

# LLM Mode

The bot supports optional LLM mode. Groq is preferred when configured.

Supported providers:

- Groq
- Gemini
- OpenAI

Recommended environment:

```env
COMPOSER_MODE=llm
REPLY_MODE=llm
GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

If no LLM key is configured, the bot still works using deterministic templates and reply handlers.

Do not commit real API keys to GitHub. Set production secrets in the Render dashboard.

---

# Local Run

Install dependencies:

```powershell
cd E:\Downloads\magicpin-ai-challenge
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the server:

```powershell
.\venv\Scripts\python.exe -m uvicorn bot:app --host 0.0.0.0 --port 8080
```

Health check:

```powershell
Invoke-RestMethod "http://localhost:8080/v1/healthz"
```

Run the judge simulator in another PowerShell window:

```powershell
.\venv\Scripts\python.exe judge_simulator.py
```

Expected local judge checks:

```text
[PASS] warmup
[PASS] auto_reply
[PASS] intent
[PASS] hostile
```

---

# Example Reply Test

```powershell
$body = @{
  conversation_id = "conv_test_001"
  merchant_id = "m_001_drmeera_dentist_delhi"
  customer_id = $null
  from_role = "merchant"
  message = "Ok lets do it. What is next?"
  received_at = "2026-07-17T10:40:00Z"
  turn_number = 2
} | ConvertTo-Json -Compress

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/v1/reply" `
  -ContentType "application/json" `
  -Body $body
```

---

# Deployment

The bot is deployable as a Render web service.

Current public base URL:

```text
https://magicpin-ai-challenge-67jm.onrender.com
```

Required endpoints:

```text
/v1/context
/v1/tick
/v1/reply
/v1/healthz
/v1/metadata
```

Render environment variables:

```text
COMPOSER_MODE=llm
REPLY_MODE=llm
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=<set as Render secret>
```

Start command:

```text
uvicorn bot:app --host 0.0.0.0 --port $PORT
```

---

# Tradeoffs

## Strengths

- Robust API contract
- Strong deterministic fallback
- Optional LLM intelligence
- Low hallucination risk through prompt and rule guardrails
- Handles auto-replies, intent transitions, hostility, waits, and repetition
- `/tick` time budget reduces timeout risk

## Limitations

- Runtime state is in memory and resets on restart
- LLM quality depends on provider availability and API key configuration
- Deterministic fallback replies are safer but less varied than full LLM output

---

# Tech Stack

- Python
- FastAPI
- Pydantic
- Uvicorn
- Groq / Llama 3.3 70B optional LLM mode
- Gemini/OpenAI optional fallback providers
- In-memory context and conversation state
- Rule-based + LLM hybrid composition
