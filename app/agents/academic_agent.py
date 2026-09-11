import time
import asyncio
import logging
import traceback

from app.core.config import settings
from app.agents.self_refining import (
    AgentEvaluator,
    ExperienceMemory,
    StrategyRefiner,
)

logger = logging.getLogger(__name__)


# =========================================================
# SELF-REFINING COMPONENTS
# =========================================================

# Academic answers have their own evaluation, memory,
# and learned strategy.
#
# They are intentionally separate from the quiz agent because
# quiz performance and academic-answer quality are different
# types of experiences.

academic_evaluator = AgentEvaluator()
academic_memory = ExperienceMemory(max_size=100)
academic_refiner = StrategyRefiner()


# =========================================================
# BASE SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = (
    "You are the Kayfa Academic Help Agent, part of the Kayfa learning platform. "
    "You help students understand concepts from their courses: explain ideas clearly, "
    "give short examples, and break down hard topics into simple steps. "
    "Always reply in the same language the student used (Arabic or English). "
    "Keep answers focused and easy to read in a chat bubble — use short paragraphs "
    "or a short list, avoid heavy markdown headers. "
    "Be warm and encouraging, like a patient tutor. "
    "If you don't know something specific to the student's course material, "
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

async def _record_experience(query: str, answer: str, course_context: str) -> None:
    """
    Runs after the student already has their answer. Evaluates the
    answer, stores it as an experience, and — every 10th experience —
    refines the learned strategy. The Groq calls involved are
    synchronous, so they're run in a thread to avoid blocking the
    event loop for other requests while this happens.
    """
    try:
        evaluation = await asyncio.to_thread(
            academic_evaluator.evaluate,
            query=query,
            answer=answer,
            course_context=course_context,
        )

        academic_memory.add(query=query, answer=answer, evaluation=evaluation)

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

        # This runs in the background, AFTER the answer is already on its
        # way back to the student. Evaluation + (occasional) refinement
        # are both extra Groq calls — doing them inline here used to make
        # the student wait on a second (sometimes third) LLM round-trip
        # before seeing their answer. That bookkeeping doesn't need to be
        # in the response path.
        asyncio.create_task(
            _record_experience(query, answer, course_context)
        )

        # =================================================
        # 10. USAGE INFORMATION
        # =================================================

        usage = {
            "latency_ms": latency_ms,
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