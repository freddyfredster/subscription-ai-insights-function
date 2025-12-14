import json
import logging
import os
import requests
import pyodbc
import azure.functions as func

app = func.FunctionApp()

# ------------------------------------------------------------
# OpenAI config (direct OpenAI API)
# ------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# ------------------------------------------------------------
# SQL config
# ------------------------------------------------------------
SQL_CONNECTION_STRING = os.getenv("SQL_CONNECTION_STRING")

# ------------------------------------------------------------
# Sample metrics payload (used for GET / quick testing)
# ------------------------------------------------------------
SAMPLE_METRICS = {
    "InsightMonth": "2025-12",
    "ScopeType": "Overall",
    "ScopeValue": "",
    "MRR": 282530,
    "MRR_MoM_Pct": 0.042,
    "Churn_M1": 0.18,
    "Churn_M2": 0.21,
    "Churn_M2_MoM": 0.03,
    "Avg_LTV": 87,
    "Avg_CAC": 64,
    "LTV_CAC": 1.36,
    "Worst_Channel": "Instagram",
    "Worst_Offer": "$1 Trial",
    "Top_Cohort": "2025-07"
}

# ------------------------------------------------------------
# Prompt building
# ------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a subscription analytics expert. "
    "Write concise, executive-ready insights for founders. "
    "Return strict JSON only. No markdown. No commentary."
)

def build_user_prompt(metrics: dict) -> str:
    return f"""
Metrics for {metrics.get("InsightMonth")} (scope: {metrics.get("ScopeType")} / {metrics.get("ScopeValue","")}):
MRR: {metrics.get("MRR")}
MRR_MoM_Pct: {metrics.get("MRR_MoM_Pct")}
Churn_M1: {metrics.get("Churn_M1")}
Churn_M2: {metrics.get("Churn_M2")} (change: {metrics.get("Churn_M2_MoM")})
Avg_LTV: {metrics.get("Avg_LTV")}
Avg_CAC: {metrics.get("Avg_CAC")}
LTV_CAC: {metrics.get("LTV_CAC")}
Worst_Channel: {metrics.get("Worst_Channel")}
Worst_Offer: {metrics.get("Worst_Offer")}
Top_Cohort: {metrics.get("Top_Cohort")}

Return JSON with:
- Narrative (max 280 characters, plain English)
- Actions (array of exactly 3 items, each max 90 characters)
- Risks (array of exactly 3 items, each max 90 characters)
""".strip()

# ------------------------------------------------------------
# OpenAI call (Responses API)
# ------------------------------------------------------------
def call_openai_for_insights(metrics: dict) -> dict:
    if not OPENAI_API_KEY:
        raise Exception("OPENAI_API_KEY environment variable not set")

    url = f"{OPENAI_BASE_URL}/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(metrics)},
        ],
        "text": {"format": {"type": "json_object"}},
        "temperature": 0.2,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    # Extract model text from nested output structure
    texts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                t = content.get("text", "")
                if t:
                    texts.append(t)

    out_text = "\n".join(texts).strip()
    if not out_text:
        raise Exception(f"Could not find output_text in response: {data}")

    try:
        obj = json.loads(out_text)
    except Exception as e:
        raise Exception(f"Model did not return valid JSON. Got: {out_text}") from e

    obj["ModelName"] = OPENAI_MODEL
    return obj

# ------------------------------------------------------------
# Validate response schema (strict)
# ------------------------------------------------------------
def validate_ai_output(obj: dict) -> dict:
    if "Narrative" not in obj or "Actions" not in obj or "Risks" not in obj:
        raise Exception(f"Invalid JSON keys. Expected Narrative, Actions, Risks. Got: {obj}")

    if not isinstance(obj["Actions"], list) or len(obj["Actions"]) != 3:
        raise Exception("Actions must be an array of exactly 3 items.")

    if not isinstance(obj["Risks"], list) or len(obj["Risks"]) != 3:
        raise Exception("Risks must be an array of exactly 3 items.")

    obj["Narrative"] = str(obj["Narrative"])[:280]
    obj["Actions"] = [str(x)[:90] for x in obj["Actions"]]
    obj["Risks"] = [str(x)[:90] for x in obj["Risks"]]

    return obj

# ------------------------------------------------------------
# SQL write (upsert to dbo.AI_Insights)
# ------------------------------------------------------------
def write_ai_insight_to_sql(metrics: dict, ai: dict) -> None:
    if not SQL_CONNECTION_STRING:
        raise Exception("SQL_CONNECTION_STRING environment variable not set")

    sql = """
    MERGE dbo.AI_Insights AS tgt
    USING (SELECT ? AS InsightMonth, ? AS ScopeType, ? AS ScopeValue) AS src
    ON  tgt.InsightMonth = src.InsightMonth
    AND tgt.ScopeType = src.ScopeType
    AND tgt.ScopeValue = src.ScopeValue
    WHEN MATCHED THEN
        UPDATE SET
            Narrative = ?,
            Action1 = ?,
            Action2 = ?,
            Action3 = ?,
            Risk1 = ?,
            Risk2 = ?,
            Risk3 = ?,
            ModelName = ?,
            GeneratedAtUTC = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT (
            InsightMonth, ScopeType, ScopeValue,
            Narrative,
            Action1, Action2, Action3,
            Risk1, Risk2, Risk3,
            ModelName
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    scope_type = metrics.get("ScopeType", "Overall")
    scope_value = metrics.get("ScopeValue", "")

    params = [
        metrics["InsightMonth"],
        scope_type,
        scope_value,

        ai["Narrative"],
        ai["Actions"][0],
        ai["Actions"][1],
        ai["Actions"][2],
        ai["Risks"][0],
        ai["Risks"][1],
        ai["Risks"][2],
        ai.get("ModelName"),

        metrics["InsightMonth"],
        scope_type,
        scope_value,
        ai["Narrative"],
        ai["Actions"][0],
        ai["Actions"][1],
        ai["Actions"][2],
        ai["Risks"][0],
        ai["Risks"][1],
        ai["Risks"][2],
        ai.get("ModelName"),
    ]

    with pyodbc.connect(SQL_CONNECTION_STRING) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()

# ------------------------------------------------------------
# HTTP trigger (GET uses sample payload; POST uses your payload)
# Persists output to SQL
# ------------------------------------------------------------
@app.function_name(name="GenerateSubscriptionInsightsHttp")
@app.route(route="insights/generate", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def GenerateSubscriptionInsightsHttp(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("AI insights HTTP trigger received")

    try:
        if req.method.upper() == "GET":
            metrics = SAMPLE_METRICS
        else:
            try:
                metrics = req.get_json()
            except Exception:
                return func.HttpResponse(
                    json.dumps({"error": "POST body must be valid JSON."}),
                    status_code=400,
                    mimetype="application/json",
                )

        if not metrics.get("InsightMonth"):
            return func.HttpResponse(
                json.dumps({"error": "InsightMonth is required (e.g. 2025-12)."}),
                status_code=400,
                mimetype="application/json",
            )

        ai = call_openai_for_insights(metrics)
        ai = validate_ai_output(ai)

        # ✅ Persist AI output into SQL
        write_ai_insight_to_sql(metrics, ai)

        return func.HttpResponse(
            json.dumps(ai, ensure_ascii=False),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as e:
        logging.exception("AI insights generation failed")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
        )

# ------------------------------------------------------------
# Timer trigger (kept, but no-op for now)
# We'll wire this later to read SQL input + write AI insights.
# ------------------------------------------------------------
@app.timer_trigger(schedule="0 0 3 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=True)
def GenerateSubscriptionInsights(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.warning("The timer is past due!")
    logging.info("Timer trigger fired (no-op for now).")
