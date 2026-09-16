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