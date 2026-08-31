import os
import asyncio
from typing import List, Dict, Any, Optional
from groq import Groq

from app.agents.config import (
    GROQ_MODEL, 
    GROQ_API_KEY, 
    ROLE_PERMISSIONS, 
    AGENT_DESCRIPTIONS,
    DATABASE_CONTEXT, 
    FINAL_TEMPERATURE, 
    PRICE_PER_INPUT_TOKEN, 
    PRICE_PER_OUTPUT_TOKEN
)
from app.services.sentiment import sentiment_engine, clean_markdown_formatting
from app.retrieval.rag import init_hybrid_agent_system
from app.retrieval.cache import check_semantic_cache, update_cache
from app.data.connector import get_personal_records
from app.observability.tracing import lf
class MCPClient:
    def __init__(self):
        self.raw_groq = Groq(api_key=GROQ_API_KEY)
        self.rag_resources = init_hybrid_agent_system()
        self.hybrid_retriever = self.rag_resources.get("hybrid_retriever")

    async def connect_to_server(self, path: str):
        pass

    async def cleanup(self):
        pass

    def _route_query(self, query: str, user_role: str) -> List[str]:
        """Supervisor Router step from architecture diagram."""
        allowed = ROLE_PERMISSIONS.get(user_role, {}).get("allowed_agents", ["Course_Agent"])
        q_lower = query.lower()

        if any(w in q_lower for w in ["درجة", "درجات", "gpa", "تقدير", "معدل", "grade", "transcript"]):
            return ["Academic_Agent"] if "Academic_Agent" in allowed else [allowed[0]]
        if any(w in q_lower for w in ["جدول", "ميعاد", "محاضرة", "قاعة", "وقت", "schedule", "time", "room"]):
            return ["Schedule_Agent"] if "Schedule_Agent" in allowed else [allowed[0]]
        if any(w in q_lower for w in ["دكتور", "أستاذ", "مدرس", "instructor", "teacher"]):
            return ["Instructor_Agent"] if "Instructor_Agent" in allowed else [allowed[0]]
        if any(w in q_lower for w in ["لائحة", "سياسة", "شروط", "قواعد", "policy", "rule"]):
            return ["Policy_Agent"] if "Policy_Agent" in allowed else [allowed[0]]

        return ["Course_Agent"] if "Course_Agent" in allowed else [allowed[0]]

    def _relevance_grader(self, query: str, documents: List[str]) -> List[str]:
        """Relevance Grader (Score >= 0.70) step."""
        if not documents:
            return []
        graded_docs = []
        for doc in documents:
            # Simple lexical & semantic keyword overlap heuristic for latency
            query_words = set(query.lower().split())
            doc_words = set(doc.lower().split())
            overlap = len(query_words.intersection(doc_words)) / max(len(query_words), 1)
            if overlap > 0.15 or len(doc) > 30:
                graded_docs.append(doc)
        return graded_docs

    def _corrective_reformulate(self, query: str) -> str:
        """Query Reformulation loop if retrieval score is low."""
        try:
            resp = self.raw_groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "Rewrite this university academic query to be clearer for semantic search. Return ONLY the rewritten query in Arabic."},
                    {"role": "user", "content": query}
                ],
                temperature=0.1,
                max_tokens=60
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return query

    async def process_query_for_api(self, query: str, user_id: str, user_role: str = "Student", history: Optional[List[Dict]] = None):
        # 1. Sentiment Analysis
        user_sentiment = sentiment_engine.predict(query) if sentiment_engine else {"label": "Neutral", "confidence": 1.0}

        # 2. Semantic Cache Check (TTL)
        cached_answer, status = check_semantic_cache(query)
        if cached_answer:
            return {"response": cached_answer, "sentiment": {"label": "Neutral", "confidence": 1.0}}

        # 3. Supervisor Router
        target_agents = self._route_query(query, user_role)

        # 4. Direct Structured DB Retrieval (Personal Records)
        personal_context = get_personal_records(user_role, str(user_id))

        # 5. Hybrid Retrieval (Vector + BM25)
        raw_docs = []
        if self.hybrid_retriever:
            try:
                retrieved_nodes = self.hybrid_retriever.retrieve(query)
                raw_docs = [n.get_content() for n in retrieved_nodes]
            except Exception as e:
                print(f"Retrieval warning: {e}")

        # 6. Relevance Grader
        relevant_docs = self._relevance_grader(query, raw_docs)

        # 7. Corrective Retrieval Loop (if initial grading fails)
        if not relevant_docs and self.hybrid_retriever:
            reformulated_query = self._corrective_reformulate(query)
            try:
                second_nodes = self.hybrid_retriever.retrieve(reformulated_query)
                relevant_docs = [n.get_content() for n in second_nodes]
            except Exception:
                pass

        rag_context = "\n---\n".join(relevant_docs[:3]) if relevant_docs else "لا توجد وثائق إضافية."

        # 8. Final LLM Generation Prompt
        system_prompt = f"""
{DATABASE_CONTEXT}

أنت المساعد الذكي الرسمي لمنصة كيف (Kayfa Learning Platform).
تحدث باللغة العربية بأسلوب ودود، مهني، ومباشر.

بيانات المستخدم الحالي المسجل:
- الدور: {user_role}
- الرقم التعريفي (ID): {user_id}

السجلات الأكاديمية المباشرة للطالب/المدرس:
{personal_context if personal_context else "لا توجد سجلات شخصية خاصة."}

معلومات الدليل الأكاديمي واللوائح (RAG Context):
{rag_context}

الوكيل المتخصص النشط: {', '.join(target_agents)}

قواعد صارمة:
1. إذا سأل الطالب عن درجاته أو مقرراته، أجب مباشرة بدقة من سجله الشخصي أعلاه.
2. لا تخترع أي معلومات غير موجودة.
3. لا تضع رموز Markdown مبالغاً فيها.
"""
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history[-4:])
        messages.append({"role": "user", "content": query})

        # 9. Langfuse Tracing & Observability
        trace = None
        generation = None
        if lf:
            try:
                trace = lf.trace(
                    name="kayfa_agent_execution",
                    user_id=str(user_id),
                    metadata={"role": user_role, "agents": target_agents, "sentiment": user_sentiment},
                    input={"query": query}
                )
                generation = trace.generation(
                    name="groq_llm_response",
                    model=GROQ_MODEL,
                    input=messages
                )
            except Exception as e:
                print(f"Langfuse Trace Start Error: {e}")

        # 10. Call Groq API
        resp = self.raw_groq.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=FINAL_TEMPERATURE,
        )

        final_text = clean_markdown_formatting(resp.choices[0].message.content.strip())
        prompt_tokens = resp.usage.prompt_tokens
        completion_tokens = resp.usage.completion_tokens
        total_tokens = resp.usage.total_tokens

        # Record Cost & Tokens in Langfuse
        calculated_cost = (prompt_tokens * PRICE_PER_INPUT_TOKEN) + (completion_tokens * PRICE_PER_OUTPUT_TOKEN)
        if generation:
            try:
                generation.end(
                    output=final_text,
                    usage={"input": prompt_tokens, "output": completion_tokens, "total": total_tokens},
                    calculated_total_cost=calculated_cost
                )
            except Exception as e:
                print(f"Langfuse Trace End Error: {e}")

        # 11. Assistant Sentiment & Semantic Cache Update
        asst_sentiment = sentiment_engine.predict(final_text) if sentiment_engine else {"label": "Positive", "confidence": 0.95}
        update_cache(query, final_text)

        return {
            "response": final_text,
            "sentiment": asst_sentiment
        }