"""AI provider interface and its two implementations.

Everything else in `speedrun_ai` depends on `CardProvider` only, never on the
Gemini SDK. Choosing an implementation is a single call to `get_provider()`.

Secret hygiene: the API key is read from the environment, kept in a private
attribute, and never placed in `repr`, `str`, `describe()` or any log record.
"""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional

from speedrun_ai.cards import CardKind

logger = logging.getLogger(__name__)

API_KEY_ENV = "GEMINI_API_KEY"
DEFAULT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_MAX_RECALL = 6
DEFAULT_MAX_PROBES = 3


class ProviderError(RuntimeError):
    """Any failure reaching or parsing the upstream model."""


@dataclass(frozen=True)
class Suggestion:
    """One card proposed by a provider, still unverified.

    `quote` must be a verbatim span of the request's source text; generation
    rejects the suggestion if it is not.
    """

    front: str
    back: str
    kind: CardKind
    quote: str

    def __post_init__(self) -> None:
        for name in ("front", "back", "quote"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("suggestion %s must be a non-empty string" % name)
        object.__setattr__(self, "kind", CardKind(self.kind))


@dataclass(frozen=True)
class GenerationRequest:
    source_id: str
    source_text: str
    topic: str
    max_recall: int = DEFAULT_MAX_RECALL
    max_probes: int = DEFAULT_MAX_PROBES

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must be a non-empty string")
        if not isinstance(self.source_text, str) or not self.source_text.strip():
            raise ValueError("source_text must be a non-empty string")
        if not isinstance(self.topic, str) or not self.topic.strip():
            raise ValueError("topic must be a non-empty string")
        if self.max_recall < 0 or self.max_probes < 0:
            raise ValueError("card limits must be non-negative")


@dataclass(frozen=True)
class ProviderConfig:
    """Everything `get_provider` needs to pick an implementation."""

    ai_enabled: bool = True
    model: str = DEFAULT_MODEL
    api_key_env: str = API_KEY_ENV


class CardProvider(ABC):
    """The only AI surface the rest of the codebase is allowed to see."""

    name = "provider"

    @property
    @abstractmethod
    def available(self) -> bool:
        """True when the provider can actually produce suggestions."""

    @property
    @abstractmethod
    def unavailable_reason(self) -> str:
        """Human-readable reason, empty when `available` is True."""

    @abstractmethod
    def describe(self) -> str:
        """Short, log-safe description. Must never contain a secret."""

    @abstractmethod
    def suggest_cards(self, request: GenerationRequest) -> List[Suggestion]:
        """Propose cards, or raise ProviderError."""


class NullProvider(CardProvider):
    """Used when AI is disabled or no key is present.

    Returns no suggestions and never raises: callers fall back to offline
    generation, which is what keeps the product working with AI switched off.
    """

    name = "null"

    def __init__(self, reason: str = "AI generation is disabled"):
        self._reason = reason

    @property
    def available(self) -> bool:
        return False

    @property
    def unavailable_reason(self) -> str:
        return self._reason

    def describe(self) -> str:
        return "NullProvider (%s)" % self._reason

    def __repr__(self) -> str:
        return "NullProvider(reason=%r)" % self._reason

    def suggest_cards(self, request: GenerationRequest) -> List[Suggestion]:
        return []


PROMPT_TEMPLATE = """You write study cards for a spaced-repetition app.

Topic: {topic}
Source id: {source_id}

Produce at most {max_recall} plain recall cards and at most {max_probes}
transfer probes.
- A recall card tests the stated fact directly.
- A transfer probe rewords the idea or applies it to a NEW situation, so that
  recognising the original wording is not enough to answer it.

Rules:
- Every card MUST include "quote": a span copied VERBATIM from the source
  below, character for character, that the card is based on. Do not paraphrase
  inside "quote". Cards whose quote is not found in the source are discarded.
- Answer only from the source. Invent nothing.

Return ONLY JSON of the form:
{{"cards": [{{"front": "...", "back": "...", "kind": "recall|probe",
"quote": "..."}}]}}

SOURCE:
{source_text}
"""


class GeminiProvider(CardProvider):
    """Gemini 2.5 Flash-Lite via the `google-genai` SDK.

    The SDK import and client construction are lazy, so building this object
    is safe with no network and no SDK installed.
    """

    name = "gemini"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        api_key_env: str = API_KEY_ENV,
    ):
        self.model = model
        self._api_key_env = api_key_env
        key = api_key if api_key is not None else os.environ.get(api_key_env, "")
        # Name-mangled and underscore-prefixed: kept off the public surface.
        self.__api_key = (key or "").strip()
        self._client: Any = None

    @property
    def available(self) -> bool:
        return bool(self.__api_key)

    @property
    def unavailable_reason(self) -> str:
        if self.available:
            return ""
        return "no %s found in the environment" % self._api_key_env

    def describe(self) -> str:
        return "GeminiProvider(model=%s, key=%s)" % (
            self.model,
            "<set:redacted>" if self.__api_key else "<unset>",
        )

    def __repr__(self) -> str:
        return self.describe()

    __str__ = __repr__

    def _load_client(self) -> Any:
        """Import the SDK and build a client. Separated out so tests can stub."""
        if self._client is None:
            from google import genai  # imported lazily on purpose

            self._client = genai.Client(api_key=self.__api_key)
        return self._client

    def suggest_cards(self, request: GenerationRequest) -> List[Suggestion]:
        if not self.available:
            raise ProviderError(self.unavailable_reason)
        prompt = PROMPT_TEMPLATE.format(
            topic=request.topic,
            source_id=request.source_id,
            max_recall=request.max_recall,
            max_probes=request.max_probes,
            source_text=request.source_text,
        )
        try:
            client = self._load_client()
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": 0.2,
                    "response_mime_type": "application/json",
                },
            )
        except ProviderError:
            raise
        except Exception as exc:
            # str(exc) from an SDK can echo request metadata but not the key,
            # which is only ever passed to the client constructor.
            raise ProviderError(
                "Gemini request failed: %s" % type(exc).__name__
            ) from None
        text = getattr(response, "text", None)
        if not text:
            raise ProviderError("Gemini returned an empty response")
        return parse_suggestions(text)


def parse_suggestions(text: str) -> List[Suggestion]:
    """Parse the model's JSON reply, tolerating markdown code fences."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    try:
        payload = json.loads(cleaned)
    except ValueError as exc:
        raise ProviderError("Gemini returned invalid JSON: %s" % exc) from None
    if isinstance(payload, dict):
        raw_cards = payload.get("cards", [])
    elif isinstance(payload, list):
        raw_cards = payload
    else:
        raise ProviderError("Gemini returned an unexpected JSON shape")

    suggestions: List[Suggestion] = []
    for raw in raw_cards:
        if not isinstance(raw, dict):
            continue
        kind_value = str(raw.get("kind", "recall")).strip().lower()
        kind = CardKind.PROBE if kind_value == "probe" else CardKind.RECALL
        try:
            suggestions.append(
                Suggestion(
                    front=str(raw.get("front", "")),
                    back=str(raw.get("back", "")),
                    kind=kind,
                    quote=str(raw.get("quote", "")),
                )
            )
        except ValueError:
            # Malformed entry: skip it rather than lose the whole batch.
            continue
    return suggestions


def get_provider(config: Optional[ProviderConfig] = None) -> CardProvider:
    """Select the provider. This is the single selection point."""
    config = config or ProviderConfig()
    if not config.ai_enabled:
        return NullProvider("AI generation is disabled by configuration")
    key = os.environ.get(config.api_key_env, "")
    if not key.strip():
        return NullProvider("no %s key found in the environment" % config.api_key_env)
    logger.debug("Selecting Gemini provider (model=%s)", config.model)
    return GeminiProvider(
        model=config.model, api_key=key, api_key_env=config.api_key_env
    )
