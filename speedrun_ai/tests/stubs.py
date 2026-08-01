"""Offline stand-ins for the AI provider.

Tests must never require a live key or network, so every test that exercises
the "AI is on" path goes through one of these.
"""

from typing import List, Sequence

from speedrun_ai.provider import (
    CardProvider,
    GenerationRequest,
    ProviderError,
    Suggestion,
)


class StubProvider(CardProvider):
    """Replays a canned list of suggestions and records the requests it saw."""

    name = "stub"

    def __init__(self, suggestions: Sequence[Suggestion]):
        self._suggestions = list(suggestions)
        self.requests: List[GenerationRequest] = []

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str:
        return ""

    def describe(self) -> str:
        return "stub provider"

    def suggest_cards(self, request: GenerationRequest) -> List[Suggestion]:
        self.requests.append(request)
        return list(self._suggestions)


class ExplodingProvider(CardProvider):
    """Simulates a provider that fails at call time (network down, quota, ...)."""

    name = "exploding"

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str:
        return ""

    def describe(self) -> str:
        return "exploding provider"

    def suggest_cards(self, request: GenerationRequest) -> List[Suggestion]:
        raise ProviderError("simulated upstream failure")


class WildProvider(CardProvider):
    """Raises a non-ProviderError exception, to prove generation still degrades."""

    name = "wild"

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str:
        return ""

    def describe(self) -> str:
        return "wild provider"

    def suggest_cards(self, request: GenerationRequest) -> List[Suggestion]:
        raise RuntimeError("something entirely unexpected")
