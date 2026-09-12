"""
Lightweight retrieval for grounding quiz generation in a course's lesson
content, without pulling in a vector DB or an embeddings API call.

The problem this replaces: `get_course()` used to grab the first 6 lessons
in whatever order Mongo returned them, hard-truncate each to 400 characters,
and join them — no relevance ranking, no coverage guarantee, and it sent
that blob on every single quiz-generation call regardless of how long or
short the actual course content was.

This module instead:
  1. Splits each lesson's content into paragraph-sized chunks.
  2. Scores every chunk against the course's own topic (title + description)
     using simple term-frequency overlap — the same "no heavy ML deps"
     approach already used in services/sentiment.py.
  3. Greedily selects the highest-scoring chunks up to a word budget, so the
     prompt only carries content that's actually relevant, capped at a
     predictable size no matter how much material the course has.

This is intentionally simple (no embeddings, no external calls) so it stays
fast, free, and dependency-free — a real embedding-based retriever could
swap in later behind the same `select_relevant_chunks` signature.
"""
import re

# Chunk target size. Lesson content is split into chunks around this many
# words so a single overly-long lesson doesn't dominate the ranking.
_CHUNK_WORDS = 120

# Total word budget for everything sent to the LLM for one quiz generation.
# Roughly ~4 chars/word => ~700 words is comfortably under 1K tokens, a big
# drop from the old worst case (6 lessons x 400 chars ~= 2400 chars each
# time, unconditionally, even when irrelevant).
_DEFAULT_WORD_BUDGET = 700

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on",
    "and", "or", "for", "with", "this", "that", "it", "as", "be", "by",
    "from", "at", "its", "into", "their", "your", "you", "can", "will",
    "في", "من", "على", "إلى", "عن", "مع", "هذا", "هذه", "التي", "الذي",
    "و", "أو", "ما", "كل", "بين",
}


def _tokenize(text: str) -> list[str]:
    return [
        t for t in re.findall(r"[\u0600-\u06FFa-zA-Z']+", text.lower())
        if t not in _STOPWORDS and len(t) > 1
    ]


def chunk_lessons(lessons: list[dict]) -> list[dict]:
    """Split a list of {title, order, content} lesson docs into
    paragraph-ish chunks of roughly _CHUNK_WORDS words each, keeping the
    parent lesson's title attached for a readable, attributable prompt."""
    chunks = []
    for lesson in sorted(lessons, key=lambda l: l.get("order", 0)):
        title = lesson.get("title", "")
        words = (lesson.get("content") or "").split()
        if not words:
            continue
        for i in range(0, len(words), _CHUNK_WORDS):
            piece = " ".join(words[i:i + _CHUNK_WORDS])
            chunks.append({"title": title, "content": piece})
    return chunks


def select_relevant_chunks(
    chunks: list[dict],
    query: str,
    word_budget: int = _DEFAULT_WORD_BUDGET,
) -> list[dict]:
    """Rank chunks by term-frequency overlap with `query` (e.g. the course
    title + description) and greedily keep the top ones until word_budget
    is hit. Falls back to natural (lesson) order if nothing scores above
    zero, so a query with no keyword overlap still returns something
    sensible instead of an empty prompt."""
    if not chunks:
        return []

    query_terms = set(_tokenize(query))
    scored = []
    for idx, chunk in enumerate(chunks):
        terms = _tokenize(chunk["content"])
        overlap = sum(1 for t in terms if t in query_terms)
        # Normalize by chunk length so long chunks don't win purely on size.
        score = overlap / max(len(terms), 1)
        scored.append((score, idx, chunk))

    any_signal = any(score > 0 for score, _, _ in scored)
    if any_signal:
        scored.sort(key=lambda x: (-x[0], x[1]))
    # else: keep original (lesson) order — natural reading order fallback.

    selected = []
    word_count = 0
    for _, _, chunk in scored:
        n_words = len(chunk["content"].split())
        if selected and word_count + n_words > word_budget:
            continue
        selected.append(chunk)
        word_count += n_words
        if word_count >= word_budget:
            break

    return selected


def build_material_text(chunks: list[dict]) -> str:
    """Join selected chunks into the plain-text block the quiz agent's
    prompt expects, grouping consecutive chunks under their lesson title."""
    lines = []
    last_title = None
    for chunk in chunks:
        if chunk["title"] != last_title:
            lines.append(f"[{chunk['title']}]")
            last_title = chunk["title"]
        lines.append(chunk["content"])
    return "\n".join(lines)


def retrieve_course_material(
    lessons: list[dict],
    query: str,
    word_budget: int = _DEFAULT_WORD_BUDGET,
) -> str:
    """End-to-end helper: chunk lessons, retrieve the most relevant ones for
    `query`, and return the ready-to-send material text."""
    chunks = chunk_lessons(lessons)
    relevant = select_relevant_chunks(chunks, query, word_budget=word_budget)
    return build_material_text(relevant)