import re

from app.agents.academic_agent import answer_academic_question
from app.agents.quiz_agent import generate_quiz_from_topic
from app.services.sentiment import analyze_sentiment

_QUIZ_TRIGGERS = re.compile(
    r"\b(quiz|test me|practice questions?)\b|"
    r"(اختبرني|اختبار|كويز|أسئلة|اسئلة)",
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


async def route_chat_message(query: str, role: str, course_context: str = "", history=None):
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

    answer, usage = await answer_academic_question(query, course_context=course_context, history=history)
    return {
        "response": answer,
        "agent": "academic_agent",
        "sentiment": sentiment,
        "usage": usage,
    }
