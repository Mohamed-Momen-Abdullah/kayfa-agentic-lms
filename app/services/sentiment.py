"""
Lightweight lexicon-based sentiment analysis for Arabic + English student
messages. This intentionally avoids heavy ML dependencies (the previous
version needed a multi-hundred-MB TensorFlow model and a pickled tokenizer
that weren't even included in the repo) in favour of a small, fast, always-
available keyword scorer. It's meant to flag an obviously frustrated or
happy student for the admin view, not to be a research-grade classifier.
"""
import re

_POSITIVE_WORDS = {
    # English
    "good", "great", "thanks", "thank", "awesome", "helpful", "love", "excellent",
    "amazing", "nice", "perfect", "clear", "understood", "easy", "cool", "appreciate",
    "happy", "glad",
    # Arabic
    "شكرا", "شكراً", "تمام", "رائع", "ممتاز", "جميل", "حلو", "مفهوم", "واضح",
    "فهمت", "حبيت", "كويس", "كويسة", "سلس", "سهل", "مبسوط", "الحمدلله",
}

_NEGATIVE_WORDS = {
    # English
    "bad", "confused", "confusing", "hard", "difficult", "hate", "frustrated",
    "frustrating", "stuck", "wrong", "annoying", "terrible", "worst", "fail",
    "failed", "cant", "can't", "cannot", "angry", "upset", "hopeless",
    # Arabic
    "صعب", "معقد", "مش", "مو", "زعلان", "متضايق", "تعبان", "غلط", "مش فاهم",
    "مافهمت", "مافهمتش", "زهقان", "مستحيل", "فاشل", "متوتر", "مضايقني",
}

_NEGATIONS = {"not", "no", "never", "لا", "مش", "مو", "ما"}


def _tokenize(text: str):
    return re.findall(r"[\u0600-\u06FFa-zA-Z']+", text.lower())


def analyze_sentiment(text: str) -> dict:
    """Return {label, confidence} for a piece of text. label is one of
    Positive / Negative / Neutral."""
    if not text or not text.strip():
        return {"label": "Neutral", "confidence": 0.5}

    tokens = _tokenize(text)
    score = 0
    hits = 0
    for i, tok in enumerate(tokens):
        negated = i > 0 and tokens[i - 1] in _NEGATIONS
        if tok in _POSITIVE_WORDS:
            score += -1 if negated else 1
            hits += 1
        elif tok in _NEGATIVE_WORDS:
            score += 1 if negated else -1
            hits += 1

    if hits == 0:
        return {"label": "Neutral", "confidence": 0.55}

    confidence = min(0.5 + (abs(score) / max(hits, 1)) * 0.4, 0.95)
    if score > 0:
        return {"label": "Positive", "confidence": round(confidence, 2)}
    if score < 0:
        return {"label": "Negative", "confidence": round(confidence, 2)}
    return {"label": "Neutral", "confidence": 0.55}
