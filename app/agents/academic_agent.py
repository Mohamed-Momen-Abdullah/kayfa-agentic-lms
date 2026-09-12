import time
import uuid
import asyncio
import logging
import traceback

from app.core.config import settings
from app.agents.self_refining import (
    AgentEvaluator,
    ExperienceMemory,
    StrategyRefiner,
)

from app.db.connector import get_db

logger = logging.getLogger(__name__)

_db = get_db()

# =========================================================
# SELF-REFINING COMPONENTS
# =========================================================

academic_evaluator = AgentEvaluator()
academic_memory = ExperienceMemory(
    max_size=100,
    collection=_db["academic_experiences"],
    agent_id="academic_agent")
academic_refiner = StrategyRefiner(
    collection=_db["academic_strategy"],
    agent_id="academic_agent")


# =========================================================
# BASE SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = (
 "You are the Kayfa Academic Help Agent, part of the Kayfa learning platform. "

    "Your job is to help students understand their courses, academic performance, "
    "grades, attendance, progress, and learning-related questions. "

    "Always reply in the same language the student used (Arabic or English). "

    # ---------------------------------------------------------
    # RESPONSE STYLE
    # ---------------------------------------------------------

    "Keep responses clean, professional, concise, and easy to read in a chat interface. "
    "Do not use unnecessary markdown formatting. "
    "Do not use bold markdown with ** unless it is genuinely necessary. "
    "Avoid excessive headings, decorative formatting, and long walls of text. "

    # ---------------------------------------------------------
    # AUTOMATIC RESPONSE FORMATTING
    # ---------------------------------------------------------

    "Choose the most appropriate response format automatically based on the student's question. "

    "For normal academic questions, use a natural conversational explanation with short paragraphs. "

    "For questions involving multiple courses, grades, attendance, completion percentages, "
    "academic statistics, or structured student performance data, prefer a clean Markdown table. "

    "For comparison questions, use a comparison table whenever multiple items or metrics "
    "are being compared. Follow the table with a short conclusion explaining the key difference. "

    "For explanation or teaching questions, prefer a clear step-by-step structure. "
    "Use numbered steps when explaining a process, concept, algorithm, or procedure. "

    "For academic dashboard summaries or requests for an overall performance summary, "
    "present the important metrics in a compact table, followed by a short Insights section "
    "containing the most useful observations and recommendations. "

    "Do not force tables when a table would not improve readability. "
    "Use the format that best matches the information being presented. "

    # ---------------------------------------------------------
    # TABLE RULES
    # ---------------------------------------------------------

    "When using a table, keep it compact and readable. "
    "Use clear column names. "
    "Keep percentages, grades, scores, and numeric values aligned logically. "
    "Do not put long explanations inside table cells. "

    # ---------------------------------------------------------
    # INSIGHTS
    # ---------------------------------------------------------

    "When the available academic data supports meaningful observations, "
    "provide a short insight or recommendation after the structured data. "
    "Do not invent statistics, grades, attendance, or conclusions that are not supported "
    "by the provided academic context. "

    # ---------------------------------------------------------
    # TEACHING STYLE
    # ---------------------------------------------------------

    "When explaining difficult concepts, break them into simple steps and use short examples "
    "when useful. "

    "Be warm and encouraging, like a patient tutor, but remain professional. "

    # ---------------------------------------------------------
    # KNOWLEDGE BOUNDARY
    # ---------------------------------------------------------

    "If you don't know something specific to the student's course material or academic data, "
    "say so plainly instead of guessing."

)


# =========================================================
# FALLBACK
# =========================================================

def _fallback_answer(query: str) -> str:
    """
    Return a fallback response when Groq is unavailable.
    """

    if any("\u0600" <= ch <= "\u06FF" for ch in query):
        return (
            f'بخصوص سؤالك عن "{query}"، محتاج مفتاح Groq API شغال '
            "عشان أقدر أجاوبك بشكل كامل ومخصص. "
            "لحد ما يتظبط ده، تقدر تسأل تاني أو تجرب الكويز من نفس الكورس."
        )

    return (
        f'To answer your question about "{query}" properly, '
        "this server needs a working Groq API key configured. "
        "In the meantime, feel free to try generating a practice "
        "quiz for your course instead."
    )


# =========================================================
# BACKGROUND: EVALUATE + STORE + PERIODICALLY REFINE
# =========================================================

async def _record_experience(query: str, answer: str, course_context: str, experience_id: str) -> None:
    """
    Runs after the student already has their answer. Evaluates the
    answer, stores it as an experience (under the id already handed
    back to the frontend, so a later thumbs up/down can find it), and —
    every 10th experience — refines the learned strategy. The Groq calls
    involved are synchronous, so they're run in a thread to avoid
    blocking the event loop for other requests while this happens.
    """
    try:
        evaluation = await asyncio.to_thread(
            academic_evaluator.evaluate,
            query=query,
            answer=answer,
            course_context=course_context,
        )

        academic_memory.add(
            query=query,
            answer=answer,
            evaluation=evaluation,
            experience_id=experience_id,
        )

        # total_seen (not len(experiences)) so this still fires exactly
        # every 10th experience once memory is full and older ones are
        # being evicted, instead of on every call.
        if academic_memory.total_seen % 10 == 0:
            refinement_result = await asyncio.to_thread(
                academic_refiner.refine, academic_memory.get_all()
            )
            logger.info(
                "Academic strategy refinement completed. "
                "Experiences=%s Strategy=%s",
                academic_memory.total_seen,
                refinement_result.get("strategy", ""),
            )
    except Exception:
        logger.error(
            "Background experience recording failed:\n%s",
            traceback.format_exc(),
        )


# =========================================================
# ACADEMIC QUESTION ANSWER
# =========================================================

async def answer_academic_question(
    query: str,
    course_context: str = "",
    history=None,
) -> tuple[str, dict]:
    """
    Generate an academic answer.

    Returns:
        (answer_text, usage_dict)

    Self-refining flow:

        Previous experiences
                ↓
        Learned strategy
                ↓
        Future system prompt
                ↓
        New answer
                ↓
        LLM evaluation
                ↓
        Experience memory
                ↓
        Strategy refinement
                ↓
        Updated strategy for future answers
    """

    history = history or []

    # =====================================================
    # 1. CHECK API KEY
    # =====================================================

    if not settings.GROQ_API_KEY:
        return _fallback_answer(query), {}


    try:
        from groq import Groq

        client = Groq(
            api_key=settings.GROQ_API_KEY
        )


        # =================================================
        # 2. GET CURRENT LEARNED STRATEGY
        # =================================================

        # This is the important part of the self-refining
        # mechanism.
        #
        # The strategy was generated from previous experiences
        # and will influence THIS future response.

        learned_strategy = academic_refiner.get_strategy()


        # =================================================
        # 3. BUILD SYSTEM MESSAGES
        # =================================================

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]


        # -------------------------------------------------
        # Add learned strategy if one exists
        # -------------------------------------------------

        if learned_strategy:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "IMPORTANT — Learned improvement strategy "
                        "from previous interactions:\n\n"
                        f"{learned_strategy}\n\n"
                        "Apply this strategy when relevant to the "
                        "student's current question. "
                        "Do not mention this strategy to the student."
                    ),
                }
            )


        # -------------------------------------------------
        # Add course context
        # -------------------------------------------------

        if course_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Context about the student's enrolled "
                        "courses and available academic information:\n\n"
                        f"{course_context}"
                    ),
                }
            )


        # =================================================
        # 4. ADD CONVERSATION HISTORY
        # =================================================

        for turn in history[-6:]:
            role = (
                "user"
                if turn.get("role") == "user"
                else "assistant"
            )

            content = turn.get(
                "content",
                "",
            )

            if content:
                messages.append(
                    {
                        "role": role,
                        "content": content,
                    }
                )


        # =================================================
        # 5. CURRENT USER QUESTION
        # =================================================

        messages.append(
            {
                "role": "user",
                "content": query,
            }
        )


        # =================================================
        # 6. GENERATE ANSWER
        # =================================================

        start_time = time.time()

        resp = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=700,
        )

        latency_ms = round(
            (time.time() - start_time) * 1000,
            1,
        )


        answer = (
            resp.choices[0]
            .message
            .content
            .strip()
        )


        # =================================================
        # 7-9. RECORD EXPERIENCE + PERIODIC REFINEMENT
        # =================================================

        # Generated now (not inside the background task) so it can be
        # handed back to the frontend immediately — the student can react
        # with thumbs up/down before the background evaluation has even
        # finished, and set_feedback() will still find the right record
        # once it's written.
        experience_id = str(uuid.uuid4())

        asyncio.create_task(
            _record_experience(query, answer, course_context, experience_id)
        )

        # =================================================
        # 10. USAGE INFORMATION
        # =================================================

        usage = {
            "latency_ms": latency_ms,
            "experience_id": experience_id,
        }

        if getattr(resp, "usage", None):
            usage["prompt_tokens"] = (
                resp.usage.prompt_tokens
            )

            usage["completion_tokens"] = (
                resp.usage.completion_tokens
            )


        # =================================================
        # 11. RETURN ANSWER
        # =================================================

        return answer, usage


    except Exception as e:

        logger.error(
            "Academic agent Groq call failed:\n%s",
            traceback.format_exc(),
        )

        return (
            f"⚠️ {_fallback_answer(query)} "
            f"({e.__class__.__name__})",
            {},
        )