import json
import time
import uuid
import logging
import traceback
import re

logger = logging.getLogger(__name__)
from app.core.config import settings


logger = logging.getLogger(__name__)


# =========================================================
# 1. AGENT EVALUATOR
# =========================================================

class AgentEvaluator:
    """
    Evaluates an AI agent response using an LLM judge.

    The evaluator looks for:
        - relevance
        - correctness
        - clarity
        - groundedness
        - recurring weaknesses

    The result is stored in ExperienceMemory and later used
    by StrategyRefiner to improve future system instructions.
    """

    EVALUATOR_PROMPT = """
You are a strict quality evaluator for an AI academic assistant.

Evaluate the assistant's answer against the user's question.

Your job is NOT to rewrite the answer.
Your job is to identify whether the answer has quality problems
that should be fixed in future responses.

Evaluate these dimensions:

1. relevance:
   Does the answer directly address the user's question?

2. correctness:
   Is the information accurate?
   Do not mark an answer incorrect simply because it is concise.

3. clarity:
   Is the explanation understandable, structured, and appropriate
   for a student?

4. groundedness:
   If course context is provided, does the answer stay grounded
   in that context and avoid unsupported claims?
   If no context is provided, evaluate based on the question itself.

Important:
- An honest statement that something is unknown is NOT automatically
  a failure.
- Do not invent weaknesses when the answer is good.
- Focus on actionable weaknesses that could improve future answers.
- If there is a specific concept the agent repeatedly explains poorly,
  identify that concept clearly.

Return ONLY valid JSON:

{
    "success": true,
    "score": 0.0,
    "strengths": [],
    "weaknesses": [],
    "reason": ""
}

Rules:
- score must be between 0.0 and 1.0
- success should normally be true when score >= 0.7
- weaknesses must contain concrete problems, not vague statements
- strengths should contain only meaningful positive observations
- reason should be short
- do not use markdown
"""

    def evaluate(
        self,
        query: str,
        answer: str,
        course_context: str = "",
    ) -> dict:
        """
        Evaluate an agent response.

        Args:
            query:
                Original user question.

            answer:
                Agent-generated answer.

            course_context:
                Optional course material/context used to judge
                groundedness and correctness.

        Returns:
            Dictionary containing evaluation information.
        """

        # -----------------------------------------------------
        # Basic validation before calling the LLM
        # -----------------------------------------------------

        if not answer or not answer.strip():
            return {
                "success": False,
                "score": 0.0,
                "strengths": [],
                "weaknesses": [
                    "The agent returned an empty answer."
                ],
                "reason": "The agent returned an empty answer.",
            }

        if not settings.GROQ_API_KEY:
            logger.warning(
                "GROQ_API_KEY is not configured. "
                "LLM evaluation skipped."
            )

            return {
                "success": True,
                "score": 1.0,
                "strengths": [],
                "weaknesses": [],
                "reason": "LLM evaluation skipped because GROQ_API_KEY is not configured.",
            }

        try:
            from groq import Groq

            client = Groq(
                api_key=settings.GROQ_API_KEY
            )

            context_section = (
                course_context
                if course_context
                else "No course context was provided."
            )

            user_prompt = (
                "USER QUESTION:\n"
                f"{query}\n\n"
                "COURSE CONTEXT:\n"
                f"{context_section}\n\n"
                "ASSISTANT ANSWER:\n"
                f"{answer}"
            )

            response = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": self.EVALUATOR_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
                temperature=0.0,
                max_tokens=500,
            )

            raw = response.choices[0].message.content.strip()
            raw = (
                raw
                .removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )

            # -------------------------------------------------
            # Extract JSON object if the model added extra text
            # -------------------------------------------------

            if not raw:
                raise ValueError("Evaluator returned an empty response.")

            match = re.search(r"\{.*\}", raw, re.DOTALL)

            if not match:
                raise ValueError(
                    f"Evaluator did not return valid JSON. Raw response: {raw!r}"
                )

            json_text = match.group(0)

            result = json.loads(json_text)

            # -------------------------------------------------
            # Normalize result
            # -------------------------------------------------

            score = float(result.get("score", 0.0))
            score = max(0.0, min(1.0, score))

            strengths = result.get("strengths", [])
            weaknesses = result.get("weaknesses", [])

            if not isinstance(strengths, list):
                strengths = [str(strengths)]

            if not isinstance(weaknesses, list):
                weaknesses = [str(weaknesses)]

            return {
                "success": score >= 0.7,
                "score": score,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "reason": str(
                    result.get("reason", "")
                ),
            }

        except Exception:
            logger.error(
                "Agent evaluation failed:\n%s",
                traceback.format_exc(),
            )

            # Do not destroy the experience pipeline if the evaluator
            # itself fails.
            return {
                "success": True,
                "score": 0.5,
                "strengths": [],
                "weaknesses": [],
                "reason": "Evaluation failed; experience was recorded without an LLM judgment.",
            }


# =========================================================
# 2. EXPERIENCE MEMORY
# =========================================================
from pymongo.collection import Collection

class ExperienceMemory:
    """
    Stores previous agent experiences.

    Now backed by MongoDB so experiences survive process restarts.
    In-memory list stays as a fast working cache; Mongo is the
    durable copy.
    """

    def __init__(
        self,
        max_size: int = 100,
        collection: Collection | None = None,
        agent_id: str = "default",
    ):
        self.max_size = max_size
        self.experiences = []
        self.total_seen = 0

        # Optional Mongo collection. If None, behaves exactly as before
        # (pure in-memory) — keeps academic_agent.py / quiz_agent.py
        # working without forcing DB wiring everywhere.
        self.collection = collection
        self.agent_id = agent_id

        if self.collection is not None:
            self._load()

    def _load(self) -> None:
        """Load the most recent experiences from Mongo on startup."""
        try:
            docs = (
                self.collection.find({"agent_id": self.agent_id})
                .sort("timestamp", -1)
                .limit(self.max_size)
            )
            loaded = list(docs)[::-1]  # oldest -> newest
            self.experiences = [
                {
                    "id": d.get("id") or str(uuid.uuid4()),
                    "query": d["query"],
                    "answer": d["answer"],
                    "evaluation": d["evaluation"],
                    "user_feedback": d.get("user_feedback"),
                    "timestamp": d["timestamp"],
                }
                for d in loaded
            ]
            self.total_seen = self.collection.count_documents(
                {"agent_id": self.agent_id}
            )
        except Exception:
            logger.error(
                "Failed to load experiences from Mongo:\n%s",
                traceback.format_exc(),
            )

    def add(self, query: str, answer: str, evaluation: dict, experience_id: str | None = None) -> str:
        """Store a new experience. Returns the experience's id (generated
        if not supplied) so callers can later attach user feedback to this
        exact record via set_feedback()."""
        experience_id = experience_id or str(uuid.uuid4())
        experience = {
            "id": experience_id,
            "query": query,
            "answer": answer,
            "evaluation": evaluation,
            "user_feedback": None,  # "up" | "down" | None, set later via set_feedback()
            "timestamp": time.time(),
        }

        self.experiences.append(experience)
        self.total_seen += 1

        if len(self.experiences) > self.max_size:
            self.experiences.pop(0)

        if self.collection is not None:
            try:
                self.collection.insert_one(
                    {**experience, "agent_id": self.agent_id}
                )
                # Optional: trim old docs in Mongo too, so the
                # collection doesn't grow forever.
                total = self.collection.count_documents(
                    {"agent_id": self.agent_id}
                )
                if total > self.max_size:
                    oldest = self.collection.find(
                        {"agent_id": self.agent_id}
                    ).sort("timestamp", 1).limit(total - self.max_size)
                    ids = [d["_id"] for d in oldest]
                    if ids:
                        self.collection.delete_many({"_id": {"$in": ids}})
            except Exception:
                logger.error(
                    "Failed to persist experience:\n%s",
                    traceback.format_exc(),
                )

        return experience_id

    def get_all(self) -> list:
        """Return all stored experiences (bounded by max_size)."""
        return self.experiences

    def get_recent(self, limit: int = 10) -> list:
        """Return the most recent `limit` experiences, newest last."""
        return self.experiences[-limit:]

    def set_feedback(self, experience_id: str, feedback: str) -> bool:
        """Attach explicit user feedback ("up"/"down") to a previously
        recorded experience, in both the in-memory cache and Mongo.
        Returns True if the experience was found and updated."""
        found = False
        for experience in self.experiences:
            if experience.get("id") == experience_id:
                experience["user_feedback"] = feedback
                found = True
                break

        if self.collection is not None:
            try:
                result = self.collection.update_one(
                    {"id": experience_id, "agent_id": self.agent_id},
                    {"$set": {"user_feedback": feedback}},
                )
                found = found or result.matched_count > 0
            except Exception:
                logger.error(
                    "Failed to persist feedback:\n%s",
                    traceback.format_exc(),
                )

        return found

    def get_feedback_counts(self) -> dict:
        """Tally of explicit user feedback across currently-held
        experiences — used by the admin dashboard to show how much real
        human signal (vs. just the LLM judging itself) is feeding into
        refinement."""
        counts = {"up": 0, "down": 0, "none": 0}
        for experience in self.experiences:
            fb = experience.get("user_feedback")
            counts[fb if fb in ("up", "down") else "none"] += 1
        return counts

# =========================================================
# 3. STRATEGY REFINER
# =========================================================

class StrategyRefiner:
    """
    Detects recurring failure patterns and converts them into
    a concise learned strategy.

    IMPORTANT:

    This does NOT train the model weights.

    Instead, it creates an additional instruction that is injected
    into future system prompts.

    Now backed by MongoDB: the learned strategy and refinement
    counters survive process restarts.

    Example:

        Repeated weakness:
        Students struggle with Big-O comparisons.

        Learned strategy:
        "When explaining Big-O notation, explicitly contrast
        O(n) and O(n²) using a small practical example."
    """

    REFINER_PROMPT = """
You are an AI agent strategy optimization system.

Your task is to analyze previous experiences of an AI academic agent
and identify REPEATED failure patterns.

The goal is to create a concise strategy that can be injected into
the agent's future system prompt.

IMPORTANT:

Do NOT simply summarize the experiences.

Look for recurring patterns.

For example:

If several experiences show problems around:
- confusing O(n) with O(n²)
- weak explanations of Big-O
- lack of practical examples for complexity

Then the strategy should become something like:

"Focus on clearly contrasting O(n) and O(n²) with a small practical
example whenever explaining Big-O notation."

Rules:

1. Do not overreact to a single bad interaction.
2. Prefer weaknesses that appear repeatedly.
3. Group similar weaknesses into one conceptual pattern.
4. Ignore one-off irrelevant mistakes.
5. The strategy must be actionable.
6. The strategy must describe HOW the future agent should respond.
7. Keep the strategy concise.
8. Each experience may include a "user_feedback" field. A value of
   "down" means the student who actually received this answer marked it
   unhelpful — treat this as a strong, reliable signal, even stronger
   than the automated evaluation score, since it reflects real human
   judgment rather than the model grading itself.
8. Do not claim that model weights were trained or changed.
9. Do not include user-specific personal information.
10. Do not rewrite the entire system prompt.
11. If there is no meaningful repeated weakness, return an empty strategy.
12. Preserve useful existing behavior when possible.

Return ONLY valid JSON:

{
    "strengths": [],
    "weaknesses": [],
    "strategy": ""
}

Where:

strengths:
Important behaviors that are already working well.

weaknesses:
Repeated problems discovered across experiences.

strategy:
One concise instruction for future responses.

Do not use markdown.
"""

    def __init__(
        self,
        collection: Collection | None = None,
        agent_id: str = "default",
    ):
        self.current_strategy = ""
        # Diagnostics for the admin dashboard: how often refinement has
        # actually been triggered, and when it last ran. Useful for
        # spotting a mis-firing trigger (running too often) or a dead one
        # (never running) at a glance.
        self.refinement_count = 0
        self.last_refined_at = None

        # Optional Mongo collection. If None, behaves exactly as
        # pure in-memory storage.
        self.collection = collection
        self.agent_id = agent_id

        if self.collection is not None:
            self._load()

    def _load(self) -> None:
        """Load the persisted strategy + counters from Mongo on startup."""
        try:
            doc = self.collection.find_one({"agent_id": self.agent_id})
            if doc:
                self.current_strategy = doc.get("strategy", "")
                self.refinement_count = doc.get("refinement_count", 0)
                self.last_refined_at = doc.get("last_refined_at")
        except Exception:
            logger.error(
                "Failed to load strategy from Mongo:\n%s",
                traceback.format_exc(),
            )

    def _persist(self) -> None:
        """Upsert the current strategy + counters into Mongo."""
        if self.collection is None:
            return

        try:
            self.collection.update_one(
                {"agent_id": self.agent_id},
                {
                    "$set": {
                        "strategy": self.current_strategy,
                        "refinement_count": self.refinement_count,
                        "last_refined_at": self.last_refined_at,
                    }
                },
                upsert=True,
            )
        except Exception:
            logger.error(
                "Failed to persist strategy:\n%s",
                traceback.format_exc(),
            )

    def refine(self, experiences: list) -> dict:
        """
        Analyze previous experiences and generate a refined strategy.

        The strategy is based on recurring patterns rather than
        individual interactions.
        """
        self.refinement_count += 1
        self.last_refined_at = time.time()
        self._persist()  # persist counters even on the early returns below

        if not experiences:
            return {
                "strengths": [],
                "weaknesses": [],
                "strategy": self.current_strategy,
            }

        if not settings.GROQ_API_KEY:
            logger.warning(
                "GROQ_API_KEY is not configured. "
                "Strategy refinement skipped."
            )

            return {
                "strengths": [],
                "weaknesses": [],
                "strategy": self.current_strategy,
            }

        try:
            from groq import Groq

            client = Groq(
                api_key=settings.GROQ_API_KEY
            )

            # -------------------------------------------------
            # Keep the refinement context bounded.
            # -------------------------------------------------

            recent_experiences = experiences[-20:]

            # -------------------------------------------------
            # We mainly care about failures and medium-quality
            # experiences because those contain useful signals.
            # -------------------------------------------------

            useful_experiences = []

            for experience in recent_experiences:
                evaluation = experience.get(
                    "evaluation",
                    {}
                )

                score = evaluation.get(
                    "score",
                    1.0
                )

                weaknesses = evaluation.get(
                    "weaknesses",
                    []
                )

                user_feedback = experience.get("user_feedback")

                # Keep failures, experiences containing explicit weaknesses,
                # and anything the student explicitly thumbs-downed — real
                # human feedback counts even when the LLM judged its own
                # answer as fine.
                if score < 0.7 or weaknesses or user_feedback == "down":
                    useful_experiences.append(
                        {
                            "query": experience.get(
                                "query",
                                ""
                            ),
                            "evaluation": evaluation,
                            "user_feedback": user_feedback,
                        }
                    )

            # If there are no problems to learn from,
            # don't invent a new strategy.
            if not useful_experiences:
                return {
                    "strengths": [
                        "No repeated quality problems were detected."
                    ],
                    "weaknesses": [],
                    "strategy": self.current_strategy,
                }

            experiences_text = json.dumps(
                useful_experiences,
                ensure_ascii=False,
                indent=2,
            )

            response = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": self.REFINER_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": (
                            "Analyze the following agent experiences "
                            "and identify recurring failure patterns.\n\n"
                            f"{experiences_text}"
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=500,
            )

            raw = response.choices[0].message.content.strip()

            # -------------------------------------------------
            # Remove accidental markdown fences
            # -------------------------------------------------

            raw = (
                raw
                .removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )

            result = json.loads(raw)

            strategy = str(
                result.get(
                    "strategy",
                    ""
                )
            ).strip()

            strengths = result.get(
                "strengths",
                []
            )

            weaknesses = result.get(
                "weaknesses",
                []
            )

            if not isinstance(strengths, list):
                strengths = [str(strengths)]

            if not isinstance(weaknesses, list):
                weaknesses = [str(weaknesses)]

            # -------------------------------------------------
            # Only replace the current strategy if the new
            # strategy is meaningful, and persist it.
            # -------------------------------------------------

            if strategy:
                self.current_strategy = strategy
                self._persist()

            return {
                "strengths": strengths,
                "weaknesses": weaknesses,
                "strategy": self.current_strategy,
            }

        except Exception:
            logger.error(
                "Strategy refinement failed:\n%s",
                traceback.format_exc(),
            )

            # Keep the previously learned strategy.
            return {
                "strengths": [],
                "weaknesses": [],
                "strategy": self.current_strategy,
            }

    def get_strategy(self) -> str:
        """
        Return the currently learned strategy.
        """

        return self.current_strategy

    def reset_strategy(self) -> None:
        """
        Reset the learned strategy.
        """

        self.current_strategy = ""
        self._persist()