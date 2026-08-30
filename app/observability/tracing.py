import os
import traceback
from langfuse import Langfuse
from langfuse.llama_index import LlamaIndexCallbackHandler
from llama_index.core.callbacks import CallbackManager

LANGFUSE_HOST = "https://us.cloud.langfuse.com"
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-d5ec3773-fab8-4872-8bbb-219dbffe63b3")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-74f7c81c-3fa8-481b-96e5-b60c1364c629")

lf = None
callback_manager = None

if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
    try:
        lf = Langfuse(public_key=LANGFUSE_PUBLIC_KEY, secret_key=LANGFUSE_SECRET_KEY, host=LANGFUSE_HOST)
        langfuse_callback_handler = LlamaIndexCallbackHandler()
        callback_manager = CallbackManager([langfuse_callback_handler])
    except Exception as e:
        print(f"⚠️ Langfuse initialization error: {e}")
else:
    print("⚠️ Langfuse keys missing — observability disabled.")

def build_langfuse_trace_url(trace_id: str) -> str:
    if not trace_id:
        return None
    return f"{LANGFUSE_HOST}/trace/{trace_id}"

def _fetch_langfuse_dashboard_data(limit: int = 100):
    if not lf:
        return {
            "status": "error", "error": "Langfuse credentials are not configured.",
            "traces": [], "kpi": {"calls_count": 0, "total_tokens": 0, "total_cost": 0.0, "unique_users": []}
        }
    try:
        traces_response = lf.get_traces(limit=limit)
        raw_traces = getattr(traces_response, "data", [])
        traces = []
        unique_users = set()

        for t in raw_traces:
            metadata = getattr(t, "metadata", {}) or {}
            routing = metadata.get("routing", {}) if isinstance(metadata, dict) else {}
            trace_input = getattr(t, "input", None) or {}
            trace_output = getattr(t, "output", None) or {}

            user_id = str(getattr(t, "user_id", None) or metadata.get("user_id") or "Unknown")
            if user_id != "Unknown":
                unique_users.add(user_id)

            traces.append({
                "id": getattr(t, "id", None),
                "timestamp": str(getattr(t, "timestamp", "")),
                "user_id": user_id,
                "user_role": str(metadata.get("user_role", "Unknown")),
                "query": trace_input.get("query", "") if isinstance(trace_input, dict) else "",
                "response": trace_output.get("response", "") if isinstance(trace_output, dict) else "",
                "user_sentiment": trace_input.get("user_sentiment") if isinstance(trace_input, dict) else None,
                "assistant_sentiment": trace_output.get("assistant_sentiment") if isinstance(trace_output, dict) else None,
                "agents": routing.get("destinations", []),
                "routing_reason": routing.get("reason", ""),
                "url": f"{LANGFUSE_HOST}/trace/{getattr(t, 'id', '')}",
            })

        gen_response = lf.get_generations(limit=limit)
        generations = getattr(gen_response, "data", [])
        total_tokens = 0
        total_cost = 0.0

        for g in generations:
            tokens = 0
            usage_details = getattr(g, "usage_details", None)
            if usage_details:
                if isinstance(usage_details, dict):
                    tokens = usage_details.get("total", 0) or usage_details.get("total_tokens", 0) or (usage_details.get("input", 0) + usage_details.get("output", 0))
                else:
                    tokens = getattr(usage_details, "total", 0) or getattr(usage_details, "total_tokens", 0)
            if not tokens:
                usage = getattr(g, "usage", None)
                if usage:
                    if isinstance(usage, dict):
                        tokens = usage.get("total_tokens", 0) or (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
                    else:
                        tokens = getattr(usage, "total_tokens", 0) or (getattr(usage, "prompt_tokens", 0) + getattr(usage, "completion_tokens", 0))
            total_tokens += int(tokens or 0)

            cost = 0.0
            cost_details = getattr(g, "cost_details", None)
            if cost_details:
                if isinstance(cost_details, dict):
                    cost = cost_details.get("total", 0) or cost_details.get("total_cost", 0)
                else:
                    cost = getattr(cost_details, "total", 0) or getattr(cost_details, "total_cost", 0)
            if not cost:
                cost = getattr(g, "calculated_total_cost", None) or getattr(g, "cost", None) or 0.0
            total_cost += float(cost or 0.0)

            gen_user = getattr(g, "user_id", None) or getattr(g, "trace_user_id", None)
            if gen_user:
                unique_users.add(str(gen_user))

        return {
            "status": "success", "traces": traces,
            "kpi": {"calls_count": len(generations), "total_tokens": total_tokens, "total_cost": total_cost, "unique_users": sorted(unique_users)}
        }
    except Exception as e:
        print("❌ Langfuse dashboard error:\n", traceback.format_exc())
        return {"status": "error", "error": str(e), "traces": [], "kpi": {"calls_count": 0, "total_tokens": 0, "total_cost": 0.0, "unique_users": []}}
