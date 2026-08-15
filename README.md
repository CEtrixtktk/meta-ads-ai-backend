# Meta Ads Analytics Dashboard with AI-Powered Performance Insights — Backend

**A platform that turns Meta Ads performance data into plain-English decisions.**

Agencies and businesses running Facebook and Instagram ads get dozens of metrics — CTR, CPC, reach, frequency — that only a specialist knows how to interpret. This platform connects to the client's ad account, pulls their real performance data, and uses AI to explain what's working, what isn't, and what to do about it, in language anyone can act on.

💻 **Frontend repository:** https://github.com/CEtrixtktk/meta-ads-ai-frontend

---

## What it solves

| Problem | How this solves it |
|---|---|
| Meta Ads reports are technical and hard to interpret | Natural-language analysis generated with Claude |
| Checking performance means digging through Ads Manager | A dedicated dashboard that centralises the metrics |
| Each agency client has their own ad account | Multi-tenant architecture with test-verified isolation |
| Access tokens are sensitive credentials | Encrypted at rest in the database |

---

## Screenshots

<img width="490" height="240" alt="0814 (2)" src="https://github.com/user-attachments/assets/805e6a6b-0833-4878-a54b-eda9db6623ca" />


---

## Stack

**Backend:** Django 5 · Django REST Framework · PostgreSQL · JWT (SimpleJWT)
**Integrations:** Meta Marketing API (Graph API v26) · Anthropic Claude API
**Testing:** pytest · pytest-django · mocked external APIs
**Infrastructure:** Railway · Gunicorn · WhiteNoise

---

## Architecture decisions

The decisions that shape this project, and the reasoning behind them:

### Business logic isolated in services

API views are deliberately thin: they validate input, delegate to a service, and return the response. All communication with Meta and Claude lives in independent modules under `services/`, one per responsibility.

The benefit is concrete: when Meta versions its API — which happens several times a year — the change is applied in a single file and no view is affected. Adding or removing features doesn't require touching the rest of the system.

### Tokens encrypted at rest

Meta access tokens can operate real ad campaigns with real spend. Storing them in plain text would expose them to any database breach.

The model encrypts tokens transparently using Fernet: a Python property encrypts on write and decrypts on read, so the rest of the codebase works with the plain value while making it impossible to store an unencrypted token by accident. The encryption key lives outside the database, in environment variables.

### Test-verified multi-tenant isolation

Django doesn't prevent one user from accessing another's data on its own — it has to be programmed into every query. Here, every query starts from the authenticated user: even if the client sends another account's identifier, the lookup happens strictly within that user's own accounts.

This guarantee is covered by an automated test that simulates one user attempting to access another's account and verifies the request is rejected before Meta is ever contacted.

### External failures translated, not propagated

Third-party APIs fail routinely: expired tokens, rate limits, outages. External calls are wrapped and their failures translated into semantically correct HTTP status codes — 502 when the external provider fails, distinct from an internal 500 or a client-side 4xx. The user gets an actionable message; the technical detail goes to the logs.

### Conversions interpreted by business model

Meta returns conversions as a list of dozens of mixed action types. The system filters for commercially meaningful ones and, critically, accounts for the fact that not every business converts through a web purchase: businesses that sell through conversation (Messenger, WhatsApp) record their conversion under a different action type entirely. Ignoring that would lead to concluding a profitable campaign generates no results.

### Decoupled integrations

The AI analysis service knows nothing about Meta: it receives a list of metrics and interprets them, regardless of origin. The orchestration layer connects the two worlds. Adding another advertising platform wouldn't require modifying the analysis module.

---

## Testing

```bash
pytest -v
```

The suite covers data transformation logic, Meta integration via mocking (consuming no tokens and requiring no network), authentication, error handling, and tenant isolation.

Mocking is a deliberate choice: the tests verify *this system's own behaviour* — that it builds requests correctly and processes responses correctly — without depending on external services, which keeps them fast, free, and deterministic.

---

## Local setup

```bash
# Environment and dependencies
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Configuration
cp .env.example .env         # fill in your own credentials

# Database
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Required environment variables are documented in `.env.example`.

---

## Project status

**Working:** JWT authentication, campaign metrics retrieval, AI-generated analysis, multi-tenant architecture, production deployment.

**In progress:** bulk campaign creation from Excel templates with asynchronous processing, and a full OAuth flow for self-service account connection.

---

## License

MIT
