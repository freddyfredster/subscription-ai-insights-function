# Subscription AI Insights Function

This repository contains a lightweight Azure Function that generates **executive-ready subscription insights** using AI.

The function takes a structured snapshot of subscription performance (e.g. MRR, churn, LTV, CAC, acquisition context), interprets it, and produces:

- A concise narrative summary
- A short list of recommended actions
- Key risks to watch

The output is designed to be **directly consumable by decision-makers** and easy to surface in tools like Power BI.

---

## What this does

At a high level, the function:

1. Accepts a monthly subscription metrics payload  
2. Sends the metrics to an AI model with a strict output schema  
3. Returns a structured insight (narrative, actions, risks)  
4. Persists the result so it can be reused by dashboards or reports  

This keeps AI interpretation **deterministic, auditable, and repeatable** rather than ad-hoc.

---

## Why this exists

Many analytics solutions stop at charts and KPIs.

This project explores how to bridge the gap between:
- **Metrics** → and →
- **Clear decisions**

The goal is not prediction, but **interpretation**: helping teams quickly understand *what changed, why it matters, and what to do next*.

---

## How it’s intended to be used

- As a backend service feeding an **AI Insights & Recommendations** page in Power BI
- As a reference implementation for structuring AI prompts around business metrics
- As a learning resource for building small, focused serverless services

You can run it locally, adapt the prompts, or extend it for your own use cases.

---

## Repository structure

```
├── function_app.py # Azure Function entry point
├── shared/
│ └── openai_client.py # OpenAI interaction logic
├── host.json
├── local.settings.json
├── requirements.txt
└── README.md

```
---

## Notes

- The function is intentionally simple and focused
- Prompts are designed to return structured JSON only
- The project favours clarity and reuse over complexity

Feel free to fork, copy, or adapt anything here.
