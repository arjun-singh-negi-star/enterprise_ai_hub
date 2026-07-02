<div align="center">

# ⚡ Enterprise AI Email Orchestrator

**A production-grade, multi-agent AI system that autonomously processes, drafts, and dispatches enterprise email responses — with human-in-the-loop approval, PII vault security, RAG knowledge retrieval, and SOC2-compliant audit logging.**

[![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-orange)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-red?logo=streamlit)](https://streamlit.io)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-darkgreen?logo=supabase)](https://supabase.com)
[![Docker](https://img.shields.io/badge/Docker-Containerized-blue?logo=docker)](https://docker.com)

[Architecture](#architecture) • [Setup](#quickstart) • [Features](#features)

</div>

---

## 📌 What is this?

Most enterprise email workflows rely on agents who manually read, think, and reply to hundreds of emails per day — slow, inconsistent, and unscalable.

This system replaces that with a **5-node LangGraph multi-agent pipeline** that:
1. Reads incoming emails from a live Gmail inbox via IMAP
2. Classifies intent (RFQ / Support / Escalation / Spam)
3. Retrieves relevant context from a vector knowledge base (Pinecone RAG)
4. Fetches client history from a Supabase CRM ledger
5. Drafts a professional, context-aware response using DeepSeek R1 → Gemini 2.5 Flash (automatic fallback)
6. Presents the draft to a human manager for approval/edit/reject
7. Dispatches the approved email via SMTP
8. Logs every action to an immutable, hash-chained SOC2 audit trail

**Result:** What took 10 minutes per email now takes ~30 seconds of human review time.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  STREAMLIT DASHBOARD                    │
│         (Live Mailbox • HITL Editor • Analytics)        │
└────────────────────┬────────────────────────────────────┘
                     │ invoke
┌────────────────────▼────────────────────────────────────┐
│              LANGGRAPH PIPELINE (5 Nodes)               │
│                                                         │
│  [1] SUPERVISOR  →  Classifies email intent             │
│       ↓              (RFQ / Support / Escalation)       │
│  [2] RAG AGENT   →  Pinecone vector search              │
│       ↓              (company policy + history)         │
│  [3] CRM AGENT   →  Supabase ledger lookup              │
│       ↓              (client interaction history)       │
│  [4] PLANNER     →  Drafts response via LLM             │
│       ↓              (DeepSeek R1 → Gemini fallback)    │
│  [5] EXECUTOR    →  SMTP dispatch after HITL approval   │
└─────────────────────────────────────────────────────────┘
         │                              │
┌────────▼────────┐          ┌─────────▼──────────┐
│   PINECONE DB   │          │  SUPABASE POSTGRES  │
│  (RAG Vectors)  │          │  (CRM + Auth + RLS) │
└─────────────────┘          └────────────────────┘
         │
┌────────▼────────┐
│  CELERY + REDIS │
│  (SLA Escalation│
│   Scheduler)    │
└─────────────────┘
```

---

## ✨ Features

| Feature | Details |
|---|---|
| 🤖 **Multi-Agent Pipeline** | 5-node LangGraph DAG — Supervisor → RAG → CRM → Planner → Executor |
| 🔀 **LLM Fallback Chain** | DeepSeek R1 (OpenRouter) → Gemini 2.5 Flash (Direct API) → DeepSeek Direct API |
| 🧠 **RAG Knowledge Base** | Upload PDF/TXT company docs → auto-chunked → Gemini embeddings → Pinecone |
| 🛡️ **PII Vault (AES-256)** | All emails masked before hitting LLM. Real values restored only at SMTP dispatch |
| 👤 **Human-in-the-Loop** | Manager can edit subject/body, approve or reject+rewrite before any email is sent |
| 📋 **Supabase CRM** | Every sent email logged. Repeat sender detection + Gmail conversation link |
| 🔒 **Semantic Leak Guard** | DLP layer — blocks email send if AI hallucinates confidential policy into draft |
| 📊 **SOC2 Audit Trail** | Immutable hash-chained JSON log of every agent action and model invocation |
| ⏰ **SLA Escalation** | Celery Beat auto-escalates unreviewed drafts: Manager → Legal → CFO |
| 🐳 **Fully Containerized** | Docker Compose — 5 services (Redis, FastAPI, Streamlit, Celery Worker + Beat) |
| 🚀 **CI/CD Pipeline** | GitHub Actions — runs graph init test + Docker build on every push to main |

---

## 🛠️ Tech Stack

**Backend:** Python 3.10, FastAPI, LangGraph, LangChain  
**AI/LLM:** DeepSeek R1, Google Gemini 2.5 Flash, OpenRouter  
**Vector DB:** Pinecone (RAG) + Google Gemini Embeddings  
**Database:** Supabase (PostgreSQL + Auth + Storage)  
**Task Queue:** Celery + Redis  
**Frontend:** Streamlit  
**Security:** AES-256-GCM PII Vault, RLS, DLP Semantic Guard  
**DevOps:** Docker, Docker Compose, GitHub Actions CI/CD  

---

## ⚡ Quickstart

### Prerequisites
- Python 3.10+
- Docker Desktop
- API Keys: OpenRouter, Google AI, Pinecone, Supabase

### 1. Clone & Setup

```bash
git clone https://github.com/arjun-singh-negi-star/enterprise_ai_hub.git
cd enterprise_ai_hub

python -m venv venv

# Windows:
.\venv\Scripts\Activate.ps1
# Mac/Linux:
source venv/bin/activate

python -m pip install -r requirements.txt
```

### 2. Environment Variables

```bash
cp .env.example .env
# Fill in your API keys in .env
```

### 3. Run (Local)

```bash
python -m streamlit run app.py
```

### 4. Run (Docker)

```bash
docker-compose up --build
```

Access: `http://localhost:8501`

---

## 🔑 Environment Variables

Create a `.env` file (see `.env.example`):

```env
# LLM
OPENROUTER_API_KEY=your_key
GOOGLE_API_KEY=your_key
DEEPSEEK_API_KEY=your_key

# Email (Gmail)
SENDER_EMAIL_ADDRESS=your@gmail.com
GMAIL_APP_PASSWORD=your_app_password

# Database
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_anon_key
DATABASE_URL=postgresql+pg8000://...

# Vector DB
PINECONE_API_KEY=your_key
PINECONE_INDEX_NAME=enterprise-rag
```

---

## 📁 Project Structure

```
enterprise_ai_hub/
├── app.py                    # Streamlit dashboard (HITL + CRM + Analytics)
├── backend/
│   ├── nodes.py              # 5 LangGraph agent nodes
│   ├── graph.py              # LangGraph pipeline definition
│   ├── state.py              # Shared agent state schema
│   ├── tools.py              # RAG + CRM tool definitions
│   ├── pii_vault.py          # AES-256-GCM PII masking/unmasking
│   ├── audit.py              # SOC2 hash-chained audit logger
│   ├── database.py           # Supabase + SQLAlchemy setup
│   ├── models.py             # SQLAlchemy ORM models
│   ├── main.py               # FastAPI app
│   └── tasks.py              # Celery SLA escalation tasks
├── knowledge_base/
│   └── pricing_compliance.txt
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── .github/
    └── workflows/
        └── deploy.yml
```

---

## 🎯 Key Design Decisions

**Why LangGraph over simple chains?**  
The pipeline needs conditional branching (SPAM emails skip RAG+CRM nodes), persistent state across HITL interrupts, and retry loops on manager rejection — all of which LangGraph handles natively.

**Why PII masking before LLM?**  
Enterprise compliance requirement. Customer emails contain names, phone numbers, and email addresses that must never be stored in third-party LLM provider logs. The vault replaces real values with tokens before any API call and restores them only at SMTP dispatch.

**Why DeepSeek R1 + Gemini fallback?**  
DeepSeek R1 provides superior chain-of-thought reasoning traces (visible to manager as "Thinking Analytics") but has limited free credits. Gemini 2.5 Flash via direct Google API serves as a reliable always-available fallback.

---

## 📈 Business Impact

| Metric | Before | After |
|---|---|---|
| Avg response draft time | 8–12 min | ~25 sec |
| Human review time | 8–12 min | ~30 sec |
| PII compliance | Manual | Automated (AES-256-GCM) |
| Audit coverage | 0% | 100% (SOC2-style) |
| Estimated US MVP value | — | $50K–$150K |

---

## 🔐 Security

- All PII masked before LLM invocation (AES-256-GCM vault)
- Supabase Row Level Security (RLS) on all tables
- Semantic DLP guard blocks hallucinated confidential data from being sent
- SOC2-style immutable audit trail with SHA-256 hash chaining
- Gmail App Password (not account password) for SMTP auth
- Secrets never committed to version control (`.gitignore` enforced)

---

<div align="center">
Built by <a href="https://github.com/arjun-singh-negi-star">Arjun Singh Negi</a>
</div>