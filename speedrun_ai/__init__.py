"""AI card generation and retrieval evaluation for Speedrun.

Self-contained: this package does not import from `anki` or `aqt`, and the
Anki layers can consume its output through `GeneratedCard.as_note()`.

The whole package works with AI disabled. `get_provider()` returns a
`NullProvider` when AI is off or no key is present, and `generate_cards()`
falls back to deterministic offline extraction rather than failing.
"""

from speedrun_ai.cards import (
    PROBE_TAG,
    TOPIC_TAG_PREFIX,
    CardKind,
    GeneratedCard,
    Provenance,
    ProvenanceError,
    topic_tag,
)
from speedrun_ai.generate import GenerationResult, generate_cards
from speedrun_ai.provider import (
    CardProvider,
    GeminiProvider,
    NullProvider,
    ProviderConfig,
    ProviderError,
    get_provider,
)

__all__ = [
    "PROBE_TAG",
    "TOPIC_TAG_PREFIX",
    "CardKind",
    "CardProvider",
    "GeminiProvider",
    "GeneratedCard",
    "GenerationResult",
    "NullProvider",
    "Provenance",
    "ProvenanceError",
    "ProviderConfig",
    "ProviderError",
    "generate_cards",
    "get_provider",
    "topic_tag",
]
