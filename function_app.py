import logging
import os
import requests
import azure.functions as func


# ------------------------------------------------------------
# App bootstrap (Azure Functions v2)
# ------------------------------------------------------------
app = func.FunctionApp()


# ------------------------------------------------------------
# OpenAI helper (direct OpenAI API, no Azure OpenAI)
# ------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")


import json
import os
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")


def generate_insight_from_openai() -> str:
    """
    Calls OpenAI Responses API and returns the model's JSON text.
    Works whether the response provides a top-level 'output_text' or nested output content.
    """

    if not OPENAI_API_KEY:
        raise Exception("OPENAI_API_KEY environment variable not set")

    url = f"{OPENAI_BASE_URL}/responses"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {
                "role": "user",
                "content": (
                    "Return JSON with a single key 'message' explaining in one sentence "
                    "why subscription churn might increase."
                )
            }
        ],
        "text": {
            "format": {"type": "json_object"}
        },
        "temperature": 0.2
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # 1) Preferred: top-level helper (some responses include this)
    out_text = data.get("output_text")
    if isinstance(out_text, str) and out_text.strip():
        return out_text

    # 2) Standard: extract from nested output -> message -> content -> output_text
    texts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                t = content.get("text", "")
                if t:
                    texts.append(t)

    out_text = "\n".join(texts).strip()
    if out_text:
        return out_text

    # 3) Final fallback: return full response so you can inspect
    raise Exception(f"Could not find output_text in response: {data}")


# ------------------------------------------------------------
# TIMER TRIGGER (kept from your original code)
# ------------------------------------------------------------
@app.timer_trigger(
    schedule="0 0 3 * * *",          # every day at 03:00
    arg_name="myTimer",
    run_on_startup=False,
    use_monitor=True
)
def GenerateSubscriptionInsights(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.warning("The timer is past due!")

    logging.info("Timer trigger fired (no business logic yet).")

    # Later this will:
    # - read SQL metrics
    # - call OpenAI
    # - write AI_Insights table


# ------------------------------------------------------------
# HTTP TRIGGER (manual / debug execution)
# ------------------------------------------------------------
@app.function_name(name="GenerateSubscriptionInsightsHttp")
@app.route(
    route="insights/generate",
    methods=["GET","POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def GenerateSubscriptionInsightsHttp(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("HTTP trigger received for AI insights")

    try:
        ai_response = generate_insight_from_openai()

        return func.HttpResponse(
            ai_response,
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.exception("Error generating AI insight")

        return func.HttpResponse(
            str(e),
            status_code=500
        )
