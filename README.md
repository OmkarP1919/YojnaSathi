# YojnaSathi

> A hackathon MVP simplifying access to government financial schemes and subsidies for citizens.

---

## 📌 Problem Statement

> **"Build a solution to simplify access to government financial schemes and subsidies for citizens."**

Citizens often miss out on impactful government welfare schemes, grants, and subsidies due to complex eligibility criteria, fragmented information, bureaucratic language, and lack of accessible communication channels.

---

## 💡 Project Description

**YojnaSathi** is an AI-powered assistant designed to bridge the gap between citizens and government welfare programs. It empowers citizens to discover, understand, and apply for schemes they are eligible for through intuitive web interactions and conversational voice/telephony access.

---

## 🛠️ Planned Technology Stack

* **Frontend:** React (Vite / TypeScript or JavaScript)
* **Backend:** Python FastAPI
* **AI & Orchestration:** LangChain / LangGraph (LLM integration & scheme matching workflow)
* **Data:** Curated Government Schemes Dataset (JSON / structured data)
* **Voice & Telephony:** Telephony integration (Twilio / voice agents) + SMS

## 📞 CALL-E Outbound Calling Setup

This MVP uses CALL-E for outbound phone calls only. The application does not currently support inbound citizen helpline calls or a public inbound number.

### Required environment variables

Copy the backend sample env file and add your CALL-E credentials:

```bash
cd backend
cp .env.example .env
```

Then set:

```env
CALLE_API_KEY=
CALLE_BASE_URL=https://api.heycall-e.com
CALLE_WEBHOOK_URL=https://your-domain.example.com/api/calle/webhook
```

Never expose the API key to the frontend. The key must remain on the backend only.

### Start the backend

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Test call initiation

Once the backend is running, trigger a call with:

```bash
curl -X POST http://localhost:8000/api/calle/call \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+919876543210", "language": "hi"}'
```

Example successful response:

```json
{
  "success": true,
  "call_id": "call_123",
  "status": "queued"
}
```

### Check call status

```bash
curl http://localhost:8000/api/calle/call/call_123
```

### Webhook endpoint

If you configure a webhook URL in CALL-E, terminal call events will be posted to:

```text
POST /api/calle/webhook
```

The backend validates the `CALL-E-Event-Id` header and extracts the final call status and structured result payload.

### Important limitation

The current implementation supports outbound calls. Inbound public helpline functionality is not implemented yet.

The current CALL-E integration in this MVP is designed for outbound calls used to initiate a short scheme-discovery conversation with a citizen. It does not implement inbound public-call handling, SMS, WhatsApp, or full autonomous call-center infrastructure.

---

## 👥 Team Responsibilities

| Contributor | Focus Area | Key Components |
| :--- | :--- | :--- |
| **Omkar** | Web Platform & AI Engine | React Frontend, FastAPI Backend, LangChain/LangGraph agent workflows, Government scheme data & eligibility matching |
| **Aditya** | Voice & Telephony Channel | Voice agent integration, Telephony, SMS notifications |

---

## 📁 Repository Structure

```text
YojnaSathi/
│
├── frontend/             # React web application
│
├── backend/              # FastAPI application & data
│   ├── app/              # Backend application code & API endpoints
│   └── data/             # Government scheme datasets & reference data
│
├── docs/                 # Documentation & architectural notes
│
├── .env.example          # Sample environment variables
├── .gitignore            # Git ignore patterns for Python, Node, & environments
└── README.md             # Project documentation
```