import json
import time
import logging
import traceback

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

class ExperienceMemory:
    """
    Stores previous agent experiences.

    Each experience contains:

        - query
        - answer
        - evaluation
        - timestamp

    The memory is intentionally bounded so it does not grow
    indefinitely during the application's lifetime.
    """

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.experiences = []
        # Total experiences ever added, NOT capped like len(experiences).
        # Used to trigger refinement every 10th experience — len() alone
        # would freeze at max_size once the buffer fills, making the
        # "every 10th" check fire on every single call from then on.
        self.total_seen = 0

    def add(
        self,
        query: str,
        answer: str,
        evaluation: dict,
    ) -> None:
        """
        Store a new agent experience.
        """

        experience = {
            "query": query,
            "answer": answer,
            "evaluation": evaluation,
            "timestamp": time.time(),
        }

        self.experiences.append(experience)
        self.total_seen += 1

        # Keep memory bounded.
        if len(self.experiences) > self.max_size:
            self.experiences.pop(0)

    def get_all(self) -> list:
        """
        Return all stored experiences.
        """

        return self.experiences

    def get_successful(self) -> list:
        """
        Return successful experiences.
        """

        return [
            experience
            for experience in self.experiences
            if experience.get(
                "evaluation",
                {}
            ).get("success") is True
        ]

    def get_failed(self) -> list:
        """
        Return failed experiences.
        """

        return [
            experience
            for experience in self.experiences
            if experience.get(
                "evaluation",
                {}
            ).get("success") is False
        ]

    def get_recent(self, limit: int = 5) -> list:
        """
        Return the most recent experiences.
        """

        return self.experiences[-limit:]

    def clear(self) -> None:
        """
        Clear all stored experiences.
        """

        self.experiences.clear()


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

    def __init__(self):
        self.current_strategy = ""
        # Diagnostics for the admin dashboard: how often refinement has
        # actually been triggered, and when it last ran. Useful for
        # spotting a mis-firing trigger (running too often) or a dead one
        # (never running) at a glance.
        self.refinement_count = 0
        self.last_refined_at = None

    def refine(self, experiences: list) -> dict:
        """
        Analyze previous experiences and generate a refined strategy.

        The strategy is based on recurring patterns rather than
        individual interactions.
        """
        self.refinement_count += 1
        self.last_refined_at = time.time()

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

                # Keep failures and experiences containing
                # explicit weaknesses.
                if score < 0.7 or weaknesses:
                    useful_experiences.append(
                        {
                            "query": experience.get(
                                "query",
                                ""
                            ),
                            "evaluation": evaluation,
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
            # strategy is meaningful.
            # -------------------------------------------------

            if strategy:
                self.current_strategy = strategy

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


# Note: no module-level singletons here on purpose. academic_agent.py and
# quiz_agent.py each create their own AgentEvaluator/ExperienceMemory/
# StrategyRefiner instances, since academic-answer quality and quiz
# performance are different experience streams (see their comments).