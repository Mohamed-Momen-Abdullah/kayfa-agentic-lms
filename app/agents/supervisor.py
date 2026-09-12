import re
import asyncio

from app.agents.academic_agent import answer_academic_question
from app.agents.quiz_agent import generate_quiz_from_topic
from app.services.sentiment import analyze_sentiment
from app.services.resource_scraper import find_study_resources
from app.db.connector import resolve_study_topic

_QUIZ_TRIGGERS = re.compile(
    r"\b(quiz|test me|practice questions?)\b|"
    r"(اختبرني|اختبار|كويز|أسئلة|اسئلة)",
    re.IGNORECASE,
)


_RESOURCE_TRIGGERS = re.compile(
    r"\b(resources?|study material|materials?|tutorials?|links?|"
    r"where (can|do) i (study|learn))\b|"
    r"(مصادر|مصدر|مذاكرة|ذاكر|روابط|لينكات|لينك|فيديوهات|مراجع)",
    re.IGNORECASE,
)


def _format_quiz_as_text(topic: str, questions: list) -> str:
    is_arabic = any("\u0600" <= ch <= "\u06FF" for ch in topic)
    lines = [f"📝 {'كويز سريع عن' if is_arabic else 'Quick quiz on'} {topic}:\n"]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q['question']}")
        letters = ["A", "B", "C", "D"]
        for j, opt in enumerate(q.get("options", [])):
            lines.append(f"   {letters[j] if j < 4 else j}. {opt}")
        lines.append("")
    correct_letters = ", ".join(
        f"{i+1}={['A','B','C','D'][q['correct_index']] if q.get('correct_index', 0) < 4 else q.get('correct_index')}"
        for i, q in enumerate(questions)
    )
    lines.append(("الإجابات: " if is_arabic else "Answers: ") + correct_letters)
    return "\n".join(lines)


async def _handle_resource_request(query: str, role: str, user_id: str, sentiment: dict) -> dict:
    """Finds study-resource links for either the course the student named
    in this message, or — if they didn't name one — their weakest course
    (see resolve_study_topic). No Groq call anywhere in this path: the
    topic lookup is a DB read and the resource lookup is a plain web
    scrape, both run in a thread so the event loop isn't blocked."""
    is_arabic = any("\u0600" <= ch <= "\u06FF" for ch in query)

    topic = resolve_study_topic(user_id, query) if role.lower() == "student" else None

    if not topic:
        response = (
            "قولّي اسم المادة أو الموضوع اللي عايز مصادر مذاكرة ليه، "
            "ولو مش عارف تختار، لسه معنديش درجات أو كويزات كفاية أحدد بيها نقطة ضعفك تلقائي."
            if is_arabic else
            "Tell me which course or topic you'd like study resources for — "
            "I don't have enough grades or quiz results yet to pick one for you automatically."
        )
        return {"response": response, "agent": "resource_agent", "sentiment": sentiment, "usage": {}}

    links = await asyncio.to_thread(find_study_resources, topic["title"])

    if not links:
        response = (
            f"مقدرتش ألاقي مصادر لـ {topic['title']} دلوقتي، جرب تاني بعد شوية."
            if is_arabic else
            f"Couldn't find resources for {topic['title']} right now — try again shortly."
        )
        return {"response": response, "agent": "resource_agent", "sentiment": sentiment, "usage": {}}

    if topic["matched"] == "named":
        header = (
            f"تمام، دي شوية مصادر تساعدك في {topic['title']}:"
            if is_arabic else
            f"Sure — here are a few resources for {topic['title']}:"
        )
    else:
        header = (
            f"شكلك محتاج تركّز على {topic['title']} — ده أضعف حاجة عندك حاليًا. "
            "دي شوية مصادر تساعدك تذاكر:"
            if is_arabic else
            f"Looks like {topic['title']} is where you're weakest right now. "
            "Here are a few resources to help you study:"
        )

    lines = [header, ""]
    for r in links:
        lines.append(f"• {r['title']}\n  {r['url']}")
    response = "\n".join(lines)

    return {"response": response, "agent": "resource_agent", "sentiment": sentiment, "usage": {}}


async def route_chat_message(query: str, role: str, course_context: str = "",
                              history=None, user_id: str | None = None):
    """Decide which agent should handle this message, run it, and return a
    unified payload: {response, agent, sentiment, usage}."""
    sentiment = analyze_sentiment(query)

    if _QUIZ_TRIGGERS.search(query):
        topic = _QUIZ_TRIGGERS.sub("", query).strip(" :،,-") or query
        questions, usage = await generate_quiz_from_topic(topic)
        response = _format_quiz_as_text(topic, questions)
        return {
            "response": response,
            "agent": "quiz_agent",
            "sentiment": sentiment,
            "usage": usage,
        }

    if _RESOURCE_TRIGGERS.search(query):
        return await _handle_resource_request(query, role, user_id, sentiment)

    answer, usage = await answer_academic_question(query, course_context=course_context, history=history)
    return {
        "response": answer,
        "agent": "academic_agent",
        "sentiment": sentiment,
        "usage": usage,
    }