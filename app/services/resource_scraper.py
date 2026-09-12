"""
Study-resource finder.

This is a plain scrape — no Groq / LLM call anywhere in this file — so a
student asking for study resources repeatedly never touches the LLM rate
limit. It hits DuckDuckGo's JS-free HTML results page (no API key needed)
for a topic and returns a short list of {title, url} links.
"""
import logging
from urllib.parse import urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://html.duckduckgo.com/html/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KayfaLMS-StudyResourceBot/1.0)"}
_TIMEOUT_SECONDS = 6


def _unwrap_ddg_redirect(href: str) -> str:
    """DuckDuckGo's HTML results wrap outbound links behind a redirect
    like //duckduckgo.com/l/?uddg=<encoded target>. Unwrap it so the
    student gets the real destination URL, not a DDG bounce link."""
    if not href:
        return href
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg")
        if target:
            return unquote(target[0])
    return href


def find_study_resources(topic: str, max_results: int = 4) -> list[dict]:
    """Scrapes a handful of study-resource links for `topic`.

    Best-effort: returns [] on any network or parsing failure instead of
    raising, so the caller can fall back to a plain "couldn't find
    anything" message rather than crashing the chat turn.
    """
    if not topic or not topic.strip():
        return []

    query = f"{topic.strip()} study guide tutorial notes"

    try:
        resp = requests.post(
            _SEARCH_URL,
            data={"q": query},
            headers=_HEADERS,
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Study-resource scrape failed for topic={topic!r}: {e}")
        return []

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for a in soup.select("a.result__a"):
            title = a.get_text(strip=True)
            url = _unwrap_ddg_redirect(a.get("href", ""))
            if title and url:
                results.append({"title": title, "url": url})
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        logger.warning(f"Study-resource parse failed for topic={topic!r}: {e}")
        return []