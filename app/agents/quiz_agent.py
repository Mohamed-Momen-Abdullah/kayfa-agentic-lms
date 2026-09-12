import json
import time
import logging
import traceback
from urllib.parse import urlencode
from urllib.request import urlopen

from app.core.config import settings
from app.agents.self_refining import ExperienceMemory, StrategyRefiner


from app.db.connector import get_db

logger = logging.getLogger(__name__)

_db = get_db()


# =========================================================
# SELF-REFINING COMPONENTS
# =========================================================

# Quiz experiences are kept separate from academic-answer
# experiences because quiz feedback is score-based and
# question-based.

quiz_memory = ExperienceMemory(
    max_size=100,
    collection=_db["quiz_experiences"],
    agent_id="quiz_agent")
quiz_refiner = StrategyRefiner(
    collection=_db["quiz_strategy"],
    agent_id="quiz_agent")


# =========================================================
# BASE QUIZ SYSTEM PROMPT
# =========================================================

QUIZ_SYSTEM_PROMPT = (
    "You generate short multiple choice quiz questions. "
    "Return ONLY a JSON array, no preamble, no markdown fences. "
    "Each item must look exactly like: "
    '{"question": "...", "options": ["...", "...", "...", "..."], "correct_index": 0}. '
    "Write in the same language as the material/topic given to you. "
    "If course material is provided, base every question strictly on it and never invent "
    "facts outside it. If only a topic is given, write general, accurate questions about it."
)


# =========================================================
# WEAKNESS REPORT PROMPT
# =========================================================

WEAKNESS_SYSTEM_PROMPT = (
    "You are an academic tutor. Based only on the multiple choice questions a student "
    "answered incorrectly, write a short, encouraging 2-3 sentence diagnostic note "
    "identifying which specific concepts the student seems weak in and should review. "
    "Reply in the same language as the material given to you. "
    "Do not repeat the raw questions verbatim; summarize the concepts instead."
)


# =========================================================
# BUILD DYNAMIC QUIZ SYSTEM PROMPT
# =========================================================

def _build_quiz_system_prompt() -> str:
    """
    Build the quiz system prompt using the currently learned
    strategy from previous student experiences.

    The learned strategy only affects FUTURE quiz generation.
    """

    learned_strategy = quiz_refiner.get_strategy()

    if not learned_strategy:
        return QUIZ_SYSTEM_PROMPT

    return (
        f"{QUIZ_SYSTEM_PROMPT}\n\n"
        "IMPORTANT — Learned improvement strategy from previous "
        "student quiz experiences:\n\n"
        f"{learned_strategy}\n\n"
        "Apply this strategy when it is relevant to the current "
        "topic or course material. "
        "Do not mention the strategy to the student."
    )


# =========================================================
# FALLBACK QUIZ
# =========================================================

def _fallback_quiz(topic: str) -> list:
    """
    Return a simple fallback quiz when Groq is unavailable.
    """

    is_arabic = any(
        "\u0600" <= ch <= "\u06FF"
        for ch in topic
    )

    if is_arabic:
        return [
            {
                "question": (
                    f"ما هو المفهوم الأساسي المرتبط بـ {topic}؟"
                ),
                "options": [
                    "مفهوم غير مرتبط",
                    "المفهوم الصحيح المرتبط بالموضوع",
                    "لا يوجد مفهوم",
                    "مفهوم متقدم فقط",
                ],
                "correct_index": 1,
            },
            {
                "question": (
                    f"هذا سؤال تجريبي لأن مفتاح Groq API "
                    f"غير مُفعّل حاليًا لموضوع {topic}."
                ),
                "options": [
                    "فعّل GROQ_API_KEY",
                    "لا يوجد حل",
                    "تجاهل الأمر",
                    "أعد التشغيل فقط",
                ],
                "correct_index": 0,
            },
        ]

    return [
        {
            "question": (
                f"What is a core idea related to {topic}?"
            ),
            "options": [
                "An unrelated idea",
                "The correct related idea",
                "No such idea exists",
                "Only advanced idea",
            ],
            "correct_index": 1,
        },
        {
            "question": (
                f"This is a placeholder question for '{topic}' "
                "because GROQ_API_KEY isn't set yet."
            ),
            "options": [
                "Set GROQ_API_KEY",
                "There's no fix",
                "Ignore it",
                "Just restart",
            ],
            "correct_index": 0,
        },
    ]


# =========================================================
# GROQ CALL
# =========================================================

def _call_groq(
    system_prompt: str,
    user_prompt: str,
    json_mode: bool = False,
):
    """
    Send a request to Groq and return:

        raw_response, usage

    If json_mode is True, Groq is asked to constrain output to a
    single valid JSON object (response_format={"type": "json_object"}).
    This only works for a top-level JSON *object*, not a JSON array,
    so it's only safe to use where the caller expects a dict.
    """

    from groq import Groq

    client = Groq(
        api_key=settings.GROQ_API_KEY
    )

    start_time = time.time()

    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        temperature=0.3,
        max_tokens=1200,
        **kwargs,
    )

    latency_ms = round(
        (time.time() - start_time) * 1000,
        1,
    )

    raw = (
        resp.choices[0]
        .message
        .content
        .strip()
    )

    # -----------------------------------------------------
    # Remove accidental markdown fences
    # -----------------------------------------------------

    raw = (
        raw
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )

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

    return raw, usage


def _safe_json_loads(raw: str):
    """
    Parse LLM-generated JSON defensively.

    Small/fast models occasionally emit near-valid JSON (a stray
    trailing comma, an unescaped quote inside a string, extra prose
    before/after the object). Before giving up, try a couple of cheap
    repairs. Raises the original JSONDecodeError if nothing works, so
    the caller's except-block and logging still fire normally.
    """

    try:
        return json.loads(raw)
    except json.JSONDecodeError as original_error:
        candidate = raw.strip()

        # Trim any stray prose before/after the JSON object or array.
        for open_ch, close_ch in (("{", "}"), ("[", "]")):
            start = candidate.find(open_ch)
            end = candidate.rfind(close_ch)
            if start != -1 and end != -1 and end > start:
                trimmed = candidate[start:end + 1]
                try:
                    return json.loads(trimmed)
                except json.JSONDecodeError:
                    pass

        # Remove common trailing-comma mistakes: ",}" / ",]"
        import re
        repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        raise original_error


# =========================================================
# GENERATE QUIZ FROM COURSE MATERIAL
# =========================================================

async def generate_quiz_from_material(
    course_title: str,
    material: str,
    n: int = 4,
) -> tuple[list, dict]:
    """
    Generate a quiz strictly grounded in course material.

    The currently learned quiz strategy is injected into the
    system prompt before generation.
    """

    if (
        not settings.GROQ_API_KEY
        or not material.strip()
    ):
        return _fallback_quiz(course_title), {}

    try:

        # -------------------------------------------------
        # Get current learned strategy
        # -------------------------------------------------

        system_prompt = _build_quiz_system_prompt()


        # -------------------------------------------------
        # Build generation prompt
        # -------------------------------------------------

        prompt = (
            f"Course: {course_title}\n\n"
            f"Material:\n{material}\n\n"
            f"Generate exactly {n} multiple choice questions."
        )


        # -------------------------------------------------
        # Generate quiz
        # -------------------------------------------------

        raw, usage = _call_groq(
            system_prompt,
            prompt,
        )


        questions = json.loads(raw)


        # -------------------------------------------------
        # Basic validation
        # -------------------------------------------------

        if not isinstance(questions, list):
            raise ValueError(
                "Quiz response is not a JSON list."
            )

        if not questions:
            raise ValueError(
                "Quiz response is empty."
            )


        return questions, usage


    except Exception:

        logger.error(
            "Quiz generation (material) failed:\n%s",
            traceback.format_exc(),
        )

        return _fallback_quiz(course_title), {}


# =========================================================
# GENERATE QUIZ FROM TOPIC
# =========================================================

async def generate_quiz_from_topic(
    topic: str,
    n: int = 3,
) -> tuple[list, dict]:
    """
    Generate a quiz from a free-text topic.

    The currently learned strategy is injected into the
    system prompt before generation.
    """

    if not settings.GROQ_API_KEY:
        return _fallback_quiz(topic), {}

    try:

        # -------------------------------------------------
        # Get current learned strategy
        # -------------------------------------------------

        system_prompt = _build_quiz_system_prompt()


        # -------------------------------------------------
        # Build topic prompt
        # -------------------------------------------------

        prompt = (
            f"Topic: {topic}\n\n"
            f"Generate exactly {n} multiple choice questions."
        )


        # -------------------------------------------------
        # Generate quiz
        # -------------------------------------------------

        raw, usage = _call_groq(
            system_prompt,
            prompt,
        )


        questions = json.loads(raw)


        # -------------------------------------------------
        # Basic validation
        # -------------------------------------------------

        if not isinstance(questions, list):
            raise ValueError(
                "Quiz response is not a JSON list."
            )

        if not questions:
            raise ValueError(
                "Quiz response is empty."
            )


        return questions, usage


    except Exception:

        logger.error(
            "Quiz generation (topic) failed:\n%s",
            traceback.format_exc(),
        )

        return _fallback_quiz(topic), {}


# =========================================================
# GRADE QUIZ
# =========================================================

def grade_quiz(
    questions: list,
    answers: dict,
) -> tuple[int, int, float, list]:
    """
    Grade the quiz.

    Returns:

        correct
        total
        score
        missed

    The missed list is later used as objective feedback
    for the self-refining system.
    """

    total = len(questions)
    correct = 0
    missed = []


    for i, q in enumerate(questions):

        # -------------------------------------------------
        # Student answer
        # -------------------------------------------------

        student_choice = answers.get(
            str(i),
            answers.get(i),
        )


        # -------------------------------------------------
        # Correctness
        # -------------------------------------------------

        is_correct = (
            student_choice is not None
            and str(student_choice)
            == str(q.get("correct_index"))
        )


        if is_correct:

            correct += 1

        else:

            options = q.get(
                "options",
                [],
            )

            correct_idx = q.get(
                "correct_index",
                0,
            )


            # ---------------------------------------------
            # Convert student's answer to integer
            # ---------------------------------------------

            try:

                student_idx = (
                    int(student_choice)
                    if student_choice is not None
                    else None
                )

            except (
                TypeError,
                ValueError,
            ):

                student_idx = None


            # ---------------------------------------------
            # Store missed question
            # ---------------------------------------------

            missed.append(
                {
                    "question": q.get(
                        "question",
                        "",
                    ),
                    "correct_answer": (
                        options[correct_idx]
                        if correct_idx < len(options)
                        else ""
                    ),
                    "student_answer": (
                        options[student_idx]
                        if (
                            student_idx is not None
                            and student_idx < len(options)
                        )
                        else "No answer"
                    ),
                }
            )


    # =====================================================
    # CALCULATE SCORE
    # =====================================================

    score = (
        round(
            (correct / total) * 10,
            1,
        )
        if total
        else 0.0
    )


    return (
        correct,
        total,
        score,
        missed,
    )


# =========================================================
# YOUTUBE RESOURCE LOOKUP (used by the improvement plan below)
# =========================================================

def _youtube_video_url(search_query: str) -> str | None:
    """Return a real YouTube watch URL when the YouTube API is configured."""
    if not settings.YOUTUBE_API_KEY or not search_query:
        return None

    params = urlencode({
        "part": "snippet",
        "q": search_query,
        "type": "video",
        "maxResults": 1,
        "key": settings.YOUTUBE_API_KEY,
    })
    try:
        with urlopen(
            f"https://www.googleapis.com/youtube/v3/search?{params}",
            timeout=5,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
        video_id = (result.get("items") or [{}])[0].get("id", {}).get("videoId")
        return f"https://www.youtube.com/watch?v={video_id}" if video_id else None
    except Exception:
        logger.warning("YouTube resource lookup failed", exc_info=True)
        return None


def _add_youtube_resources(plan: dict, course_title: str) -> dict:
    """Attach verified YouTube URLs, or precise YouTube search URLs."""
    for week in plan.get("weeks", []):
        for day in week.get("days", []):
            for resource in day.get("resources", []):
                query = resource.get("search_query") or day.get("focus") or day.get("title", "")
                scoped_query = f"{course_title} {query}".strip()
                resource["url"] = _youtube_video_url(scoped_query) or (
                    "https://www.youtube.com/results?" + urlencode({"search_query": scoped_query})
                )
                resource["provider"] = "YouTube"
    return plan


# =========================================================
# IMPROVEMENT PLAN PROMPT
# =========================================================

IMPROVEMENT_PLAN_SYSTEM_PROMPT = (
    "You are an academic coach. A student just took a quiz and missed some "
    "questions. Based ONLY on the missed questions (and course material, if "
    "given), build a short, time-ordered study plan to help them reach a "
    "perfect score next time. "
    "Return ONLY valid JSON, no markdown fences, no preamble, in exactly "
    "this shape: "
    '{"diagnosis": "1-2 sentence summary of the pattern in what they got wrong", '
    '"weeks": [{"title": "Week 1", "days": [{"day": "Day 1", "title": "concept to study", '
    '"focus": "specific concept", "task": "concrete practice task", '
    '"resources": [{"title": "resource or teacher name", "provider": "person or platform", '
    '"search_query": "exact terms the student can search externally"}]}]}], '
    '"project": {"title": "short hands-on project name", "description": "1-2 sentences describing '
    'a small task that applies the weak concepts"}, '
    '"look_into": ["specific concept or term to search or review", "..."]}. '
    "Rules: create 1 or 2 weeks and 2 to 4 days per week. Each day must contain "
    "one specific concept and one concrete action (re-read X, practice Y, redo "
    "the quiz on Z), never vague encouragement. Include 1 or 2 useful resources "
    "per day. Resource search_query values may be searched externally, but do "
    "not invent URLs. "
    "\"look_into\" items must be specific concepts or terms only — never URLs, "
    "website names, or book titles, since those would just be invented; the "
    "student will search for these themselves. "
    "If course material is given, ground every step and look_into item in it "
    "and do not invent facts outside it. "
    "Reply in the same language as the missed questions. "
    "No markdown formatting inside the JSON string values."
)


# =========================================================
# IMPROVEMENT PLAN
# =========================================================

def generate_improvement_plan(
    course_title: str,
    missed: list,
    score: float,
    course_material: str = "",
) -> dict:
    """
    Turns quiz mistakes into a structured improvement plan: a short
    diagnosis, ordered concrete steps, a small hands-on project, and
    specific concepts to look into.

    "look_into" is deliberately terms/concepts, never links — the LLM
    has no way to verify a URL actually exists or is still live, so
    generating one here would just be a plausible-looking hallucination.
    Grounding in course_material (when available) keeps the plan tied
    to what the student was actually taught rather than the model's
    general knowledge of the topic.
    """

    if not missed:
        return {
            "diagnosis": "Perfect score — no weak spots found this time.",
            "weeks": [],
            "project": None,
            "look_into": [],
        }

    if not settings.GROQ_API_KEY:
        topics = [m["question"] for m in missed[:3]]
        return _add_youtube_resources({
            "diagnosis": f"You'll want to review: {'; '.join(topics)}",
            "weeks": [{
                "title": "Week 1",
                "days": [{
                    "day": f"Day {i + 1}",
                    "title": f"Review: {topic}",
                    "focus": topic,
                    "task": "Re-read the related lesson material and answer five practice questions.",
                    "resources": [{
                        "title": f"Search for {topic}",
                        "provider": "External search",
                        "search_query": topic,
                    }],
                } for i, topic in enumerate(topics)],
            }],
            "project": None,
            "look_into": topics,
        }, course_title)

    lines = "\n".join(
        (
            f"- Question: {m['question']} | "
            f"Correct answer: {m['correct_answer']} | "
            f"Student picked: {m['student_answer']}"
        )
        for m in missed
    )

    prompt = (
        f"Course: {course_title}\n"
        f"Current score: {score}/10\n"
        f"Questions the student got wrong:\n{lines}\n"
    )

    if course_material:
        prompt += f"\nCourse material excerpt (ground your plan in this):\n{course_material[:3000]}\n"

    raw = None

    try:
        raw, _usage = _call_groq(
            IMPROVEMENT_PLAN_SYSTEM_PROMPT,
            prompt,
            json_mode=True,
        )

        plan = _safe_json_loads(raw)

        if not isinstance(plan, dict):
            raise ValueError("Improvement plan response is not a JSON object.")

        plan.setdefault("diagnosis", "")
        plan.setdefault("weeks", [])
        plan.setdefault("project", None)
        plan.setdefault("look_into", [])

        return _add_youtube_resources(plan, course_title)

    except Exception:
        logger.error(
            "Improvement plan generation failed. Raw model output: %r\n%s",
            raw,
            traceback.format_exc(),
        )

        return {
            "diagnosis": (
                "We couldn't generate a detailed plan this time, "
                "but keep practicing the topics you missed above."
            ),
            "weeks": [],
            "project": None,
            "look_into": [],
        }


# =========================================================
# WEAKNESS REPORT (kept as a plain-text fallback / used elsewhere)
# =========================================================

def generate_weakness_report(
    course_title: str,
    missed: list,
) -> str:
    """
    Generate a short diagnostic report describing
    concepts the student should review.
    """

    if not missed:
        return (
            "Great job! You answered every question correctly — "
            "no weak spots found this time."
        )


    if not settings.GROQ_API_KEY:

        topics = "; ".join(
            m["question"]
            for m in missed[:3]
        )

        return (
            f"You'll want to review: {topics}"
        )


    lines = "\n".join(
        (
            f"- Question: {m['question']} | "
            f"Correct answer: {m['correct_answer']} | "
            f"Student picked: {m['student_answer']}"
        )
        for m in missed
    )


    prompt = (
        f"Course: {course_title}\n"
        f"Questions the student got wrong:\n"
        f"{lines}"
    )


    try:

        raw, _usage = _call_groq(
            WEAKNESS_SYSTEM_PROMPT,
            prompt,
        )

        return raw


    except Exception:

        logger.error(
            "Weakness report generation failed:\n%s",
            traceback.format_exc(),
        )

        return (
            "We couldn't generate a detailed review this time, "
            "but keep practicing the topics you missed above."
        )


# =========================================================
# REFINE QUIZ EXPERIENCE
# =========================================================

def refine_quiz_experience(
    topic: str,
    questions: list,
    score: float,
    missed: list,
) -> dict:
    """
    Store a student's quiz performance and periodically
    refine the quiz-generation strategy.

    Self-refining flow:

        Quiz
          ↓
        Student answers
          ↓
        Objective score
          ↓
        Missed questions
          ↓
        ExperienceMemory
          ↓
        Every 10 experiences
          ↓
        StrategyRefiner
          ↓
        Learned strategy
          ↓
        Future quizzes

    IMPORTANT:

    The strategy affects FUTURE quizzes only.
    It does not modify the quiz that has already been graded.
    """


    # =====================================================
    # STORE THE QUIZ QUESTIONS
    # =====================================================

    quiz_data = [
        {
            "question": q.get(
                "question",
                "",
            ),
            "options": q.get(
                "options",
                [],
            ),
            "correct_index": q.get(
                "correct_index",
                0,
            ),
        }
        for q in questions
    ]


    # =====================================================
    # CREATE OBJECTIVE EVALUATION
    # =====================================================

    evaluation = {
        "success": score >= 7.0,
        "score": score / 10,
        "reason": (
            f"Student scored {score}/10."
        ),
        "missed": missed,
    }


    # =====================================================
    # STORE EXPERIENCE
    # =====================================================

    quiz_memory.add(
        query=topic,
        answer=json.dumps(
            quiz_data,
            ensure_ascii=False,
        ),
        evaluation=evaluation,
    )


    # =====================================================
    # CHECK MEMORY SIZE
    # =====================================================

    experiences = quiz_memory.get_all()

    # total_seen (not len(experiences)) so this fires exactly every 10th
    # experience even after the buffer is full and old ones are evicted —
    # len() alone freezes at max_size, which made this fire on every call.
    experience_count = quiz_memory.total_seen


    # =====================================================
    # PERIODIC STRATEGY REFINEMENT
    # =====================================================
    if experience_count % 10 == 0:

        refinement_result = quiz_refiner.refine(
            experiences
        )

        logger.info(
            "Quiz strategy refinement completed. "
            "Experiences=%s Strategy=%s",
            experience_count,
            refinement_result.get(
                "strategy",
                "",
            ),
        )

        return refinement_result


    # =====================================================
    # NO REFINEMENT THIS TIME
    # =====================================================

    return {
        "strengths": [],
        "weaknesses": [],
        "strategy": quiz_refiner.get_strategy(),
    }