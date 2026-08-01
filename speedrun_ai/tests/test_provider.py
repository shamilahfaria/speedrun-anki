"""Provider selection + secret-hygiene tests.

None of these tests may touch the network or require a real API key.
"""

import logging

import pytest

from speedrun_ai import provider as P

FAKE_KEY = "AIzaSy-TEST-KEY-DO-NOT-LOG-0123456789"


def _public_attr_values(obj):
    values = []
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            values.append(getattr(obj, name))
        except Exception:  # pragma: no cover - defensive
            continue
    return values


def test_both_implementations_share_the_interface():
    assert issubclass(P.NullProvider, P.CardProvider)
    assert issubclass(P.GeminiProvider, P.CardProvider)


def test_selection_is_one_call_and_returns_null_when_ai_disabled(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    prov = P.get_provider(P.ProviderConfig(ai_enabled=False))
    assert isinstance(prov, P.NullProvider)
    assert prov.available is False
    assert "disabled" in prov.unavailable_reason.lower()


def test_selection_returns_null_when_no_key_present(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    prov = P.get_provider(P.ProviderConfig(ai_enabled=True))
    assert isinstance(prov, P.NullProvider)
    assert prov.available is False
    assert "key" in prov.unavailable_reason.lower()


def test_selection_returns_null_when_key_is_blank(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    prov = P.get_provider(P.ProviderConfig(ai_enabled=True))
    assert isinstance(prov, P.NullProvider)


def test_selection_returns_gemini_when_enabled_and_key_present(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    prov = P.get_provider(P.ProviderConfig(ai_enabled=True))
    assert isinstance(prov, P.GeminiProvider)
    assert prov.model == "gemini-2.5-flash-lite"
    assert prov.available is True


def test_get_provider_defaults_to_env_only(monkeypatch):
    """get_provider() with no arguments must still work (one function call)."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    prov = P.get_provider()
    assert isinstance(prov, P.CardProvider)


def test_constructing_gemini_provider_does_not_touch_network(monkeypatch):
    """The SDK/client must be created lazily, so construction is offline-safe."""
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    prov = P.GeminiProvider()  # must not raise even with no google-genai installed
    assert prov.model == "gemini-2.5-flash-lite"


def test_api_key_never_appears_in_repr_str_or_logs(monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    with caplog.at_level(logging.DEBUG):
        prov = P.get_provider(P.ProviderConfig(ai_enabled=True))
        assert FAKE_KEY not in repr(prov)
        assert FAKE_KEY not in str(prov)
        logged = "\n".join(rec.getMessage() for rec in caplog.records)
        assert FAKE_KEY not in logged
    for value in _public_attr_values(prov):
        assert value != FAKE_KEY
        assert not (isinstance(value, str) and FAKE_KEY in value)


def test_describe_is_safe_to_log(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    prov = P.get_provider(P.ProviderConfig(ai_enabled=True))
    assert FAKE_KEY not in prov.describe()
    assert "gemini-2.5-flash-lite" in prov.describe()


def test_null_provider_returns_no_suggestions_without_raising():
    prov = P.NullProvider("ai disabled")
    request = P.GenerationRequest(
        source_id="doc-1",
        source_text="Glycolysis occurs in the cytosol.",
        topic="Biology",
        max_recall=3,
        max_probes=2,
    )
    assert prov.suggest_cards(request) == []


def test_generation_request_rejects_empty_source():
    with pytest.raises(ValueError):
        P.GenerationRequest(source_id="doc-1", source_text="   ", topic="Biology")
    with pytest.raises(ValueError):
        P.GenerationRequest(source_id="", source_text="text", topic="Biology")


def test_gemini_suggest_cards_raises_provider_error_when_sdk_missing(monkeypatch):
    """Offline/no-SDK must surface as ProviderError, never an arbitrary crash."""
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    prov = P.GeminiProvider()
    monkeypatch.setattr(prov, "_load_client", _raise_import_error)
    request = P.GenerationRequest(
        source_id="doc-1",
        source_text="Glycolysis occurs in the cytosol.",
        topic="Biology",
    )
    with pytest.raises(P.ProviderError):
        prov.suggest_cards(request)


def test_gemini_raises_provider_error_when_response_is_empty(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    prov = P.GeminiProvider()
    monkeypatch.setattr(prov, "_load_client", lambda: _FakeClient(""))
    with pytest.raises(P.ProviderError):
        prov.suggest_cards(_request())


def test_gemini_wraps_transport_failures_as_provider_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    prov = P.GeminiProvider()
    failing = _FailingClient()
    monkeypatch.setattr(prov, "_load_client", lambda: failing)
    with pytest.raises(P.ProviderError):
        prov.suggest_cards(_request())


def test_gemini_happy_path_parses_suggestions_and_sends_the_right_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    prov = P.GeminiProvider()
    client = _FakeClient(
        '{"cards": [{"front": "Where does glycolysis occur?",'
        ' "back": "Cytosol.", "kind": "recall",'
        ' "quote": "Glycolysis occurs in the cytosol"},'
        ' {"front": "Apply it", "back": "...", "kind": "probe",'
        ' "quote": "in the cytosol"}]}'
    )
    monkeypatch.setattr(prov, "_load_client", lambda: client)
    suggestions = prov.suggest_cards(_request())
    assert [s.kind for s in suggestions] == [P.CardKind.RECALL, P.CardKind.PROBE]
    assert suggestions[0].quote == "Glycolysis occurs in the cytosol"
    assert client.calls[0]["model"] == "gemini-2.5-flash-lite"
    # The prompt must carry the source, and must never carry the key.
    assert "Glycolysis occurs in the cytosol." in client.calls[0]["contents"]
    assert FAKE_KEY not in client.calls[0]["contents"]


def test_parse_suggestions_handles_markdown_code_fences():
    text = '```json\n{"cards": [{"front": "f", "back": "b", "kind": "probe",\n"quote": "q"}]}\n```'
    suggestions = P.parse_suggestions(text)
    assert len(suggestions) == 1
    assert suggestions[0].kind is P.CardKind.PROBE


def test_parse_suggestions_accepts_a_bare_list():
    text = '[{"front": "f", "back": "b", "kind": "recall", "quote": "q"}]'
    assert len(P.parse_suggestions(text)) == 1


def test_parse_suggestions_defaults_unknown_kinds_to_recall():
    text = '[{"front": "f", "back": "b", "kind": "banana", "quote": "q"}]'
    assert P.parse_suggestions(text)[0].kind is P.CardKind.RECALL


def test_parse_suggestions_skips_malformed_entries_without_losing_the_batch():
    text = (
        '{"cards": [{"front": "", "back": "b", "kind": "recall", "quote": "q"},'
        ' "not-an-object",'
        ' {"front": "f", "back": "b", "kind": "recall", "quote": "q"}]}'
    )
    suggestions = P.parse_suggestions(text)
    assert len(suggestions) == 1
    assert suggestions[0].front == "f"


def test_parse_suggestions_rejects_invalid_json():
    with pytest.raises(P.ProviderError):
        P.parse_suggestions("this is not json at all")


def test_parse_suggestions_rejects_unexpected_json_shape():
    with pytest.raises(P.ProviderError):
        P.parse_suggestions('"just a string"')


def _request():
    return P.GenerationRequest(
        source_id="doc-1",
        source_text="Glycolysis occurs in the cytosol.",
        topic="Biology",
    )


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text, calls):
        self._text = text
        self._calls = calls

    def generate_content(self, **kwargs):
        self._calls.append(kwargs)
        return _FakeResponse(self._text)


class _FakeClient:
    """Stands in for genai.Client. No network, no SDK required."""

    def __init__(self, text):
        self.calls = []
        self.models = _FakeModels(text, self.calls)


class _FailingModels:
    def generate_content(self, **kwargs):
        raise OSError("connection refused")


class _FailingClient:
    def __init__(self):
        self.models = _FailingModels()


def _raise_import_error():
    raise ImportError("google-genai is not installed")
