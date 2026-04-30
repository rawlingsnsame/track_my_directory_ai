"""
AI Client configuration and API handling.

Supports multiple models with automatic fallback on failure.
"""
import os
import json
import logging
from typing import Dict, List, Optional

from openai import OpenAI, APIError, APITimeoutError, AuthenticationError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("zila.config")

ROUTER_SYSTEM_PROMPT = """
You are the planning step of a directory analysis agent.

Your only job is to read a user's question about a code repository
and return a JSON list of tools needed to answer it.

Available tools:
- directory_tree: the list of all tracked files in the repo
- recent_commits: last 20 commits with messages and changed files
- uncommitted_changes: any staged or unstaged work in progress
- last_diff: the full code diff introduced by the most recent commit
- read_readme: reads the README file of the project

Rules:
- Return ONLY a raw JSON array. No explanation, no markdown, no prose.
- Choose the minimum set of tools needed. Don't over-fetch.
- If the question is about recent activity or history, include recent_commits.
- If the question is about current unfinished work, include uncommitted_changes.
- If the question is about what the last commit did, include last_diff.
- If the question is about project structure or what files exist, include directory_tree.
- You may combine tools when the question spans multiple concerns.

Examples:
  "what has been worked on recently?" -> ["recent_commits"]
  "what am i currently working on?" -> ["uncommitted_changes"]
  "what does this project look like?" -> ["directory_tree", "recent_commits"]
  "what did the last commit change?" -> ["last_diff"]
  "what is this project about?" -> ["read_readme"] and read other .md files if README is shallow
""".strip()


class AIResponseError(Exception):
    """Raised when all models fail or return unusable responses."""
    pass


class AIClient:
    """
    Handles API calls with model fallback.

    Models are tried in order until one succeeds. Each model gets one attempt
    by default to minimize latency.
    """

    # Default model list (ordered by preference/cost)
    DEFAULT_MODELS = [
        "google/gemini-2.5-flash-lite",  # Primary - fast, cheap
        "meta-llama/llama-4-scout",      # Free fallback
        "mistralai/mistral-nemo",        # Another free option
    ]

    def __init__(
        self,
        models: Optional[List[str]] = None,
        timeout: int = 60,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.models = models or self.DEFAULT_MODELS
        self.timeout = timeout

        # Get credentials from env or parameters
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = base_url or os.getenv("OPENROUTER_BASE_URL")

        if not self.api_key:
            log.error("OPENROUTER_API_KEY not set in environment")
            raise ValueError("OPENROUTER_API_KEY environment variable is required")

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

    def _parse_json_response(self, raw: str) -> List[str]:
        """Parse JSON response, handling common formatting issues."""
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
                return parsed
            if isinstance(parsed, dict):
                # Grab the first list value found
                for v in parsed.values():
                    if isinstance(v, list):
                        return v
            return []
        except json.JSONDecodeError as e:
            log.debug(f"JSON parse failed: {e}")
            return []

    def call_router(self, question: str) -> List[str]:
        """
        Call the router to determine which tools are needed.
        Returns a list of tool names.
        """
        errors: Dict[str, str] = {}

        for model in self.models:
            try:
                log.info("Routing via %s", model)
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                        {"role": "user", "content": question}
                    ],
                    timeout=self.timeout,
                )

                raw = response.choices[0].message.content
                if not raw:
                    log.warning("Empty response from %s", model)
                    continue

                result = self._parse_json_response(raw)
                if result:
                    return result

                log.warning("No valid tools found in response from %s", model)

            except APITimeoutError as e:
                errors[model] = f"Timeout: {e}"
                log.warning("Model %s timed out", model)
            except AuthenticationError as e:
                log.error("Authentication failed: %s", e)
                raise AIResponseError(f"API authentication failed: {e}")
            except APIError as e:
                errors[model] = f"API Error: {e}"
                log.warning("Model %s API error: %s", model, e)
            except Exception as e:
                errors[model] = f"{type(e).__name__}: {e}"
                log.warning("Model %s failed: %s", model, errors[model])

        if errors:
            raise AIResponseError(
                f"All models failed:\n" + "\n".join(f"  {m}: {e}" for m, e in errors.items())
            )
        return []

    def call_answerer(self, messages: list, system_prompt: str) -> str:
        """
        Call the answerer to generate a final response.
        """
        errors: Dict[str, str] = {}

        for model in self.models:
            try:
                log.info("Answering via %s", model)
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system_prompt}] + messages,
                    timeout=self.timeout,
                )
                content = response.choices[0].message.content
                if content:
                    return content
                log.warning("Empty response from %s", model)

            except APITimeoutError as e:
                errors[model] = f"Timeout: {e}"
                log.warning("Model %s timed out", model)
            except AuthenticationError as e:
                log.error("Authentication failed: %s", e)
                raise AIResponseError(f"API authentication failed: {e}")
            except APIError as e:
                errors[model] = f"API Error: {e}"
                log.warning("Model %s API error: %s", model, e)
            except Exception as e:
                errors[model] = f"{type(e).__name__}: {e}"
                log.warning("Model %s failed: %s", model, errors[model])

        if errors:
            raise AIResponseError(
                f"All models failed:\n" + "\n".join(f"  {m}: {e}" for m, e in errors.items())
            )
        raise AIResponseError("No response from any model")

    def call_agent(self, messages: list, system_prompt: str) -> str:
        """
        Single model call for the agent loop.
        Unlike call_answerer, this is called repeatedly with growing
        history — the caller manages the conversation state.
        Returns raw text so the agent loop can parse THOUGHT/ACTION/ANSWER.
        """
        errors: Dict[str, str] = {}

        for model in self.models:
            try:
                log.info("Agent step via %s", model)
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system_prompt}] + messages,
                    timeout=self.timeout,
                )
                content = response.choices[0].message.content
                if content:
                    return content.strip()
                log.warning("Empty response from %s", model)

            except APITimeoutError as e:
                errors[model] = f"Timeout: {e}"
                log.warning("Model %s timed out", model)
            except AuthenticationError as e:
                log.error("Authentication failed: %s", e)
                raise AIResponseError(f"API authentication failed: {e}")
            except APIError as e:
                errors[model] = f"API Error: {e}"
                log.warning("Model %s API error: %s", model, e)
            except Exception as e:
                errors[model] = f"{type(e).__name__}: {e}"
                log.warning("Model %s failed: %s", model, errors[model])

        if errors:
            raise AIResponseError(
                f"All models failed:\n" + "\n".join(f"  {m}: {e}" for m, e in errors.items())
            )
        raise AIResponseError("No response from any model")


# Global client instance
_evaluator: Optional[AIClient] = None


def get_client() -> AIClient:
    """Get or create the global AI client instance."""
    global _evaluator
    if _evaluator is None:
        try:
            _evaluator = AIClient()
        except ValueError as e:
            log.error("Failed to initialize AI client: %s", e)
            raise
    return _evaluator


def get_tools_needed(prompt: str) -> List[str]:
    """Route a question to determine which tools are needed."""
    return get_client().call_router(prompt)


def get_answer(messages: list, system_prompt: str) -> str:
    """Generate an answer from messages and system prompt."""
    if not system_prompt:
        raise ValueError("system_prompt is required")
    return get_client().call_answerer(messages, system_prompt)


def call_agent_step(messages: list, system_prompt: str) -> str:
    """Call the agent for one reasoning step."""
    return get_client().call_agent(messages, system_prompt)
