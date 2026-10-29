from app.agent.llm_client import GeminiLLMClient
from app.api.deps import get_interviewer


def test_interviewer_gets_api_key_from_settings_not_environment(monkeypatch):
    """The server reads the key with pydantic-settings, which does not put it into
    os.environ. So the Gemini client must receive it as an argument; if it still looks
    in the environment, building it fails with "No API key was provided"."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_interviewer.cache_clear()
    try:
        interviewer = get_interviewer()  # builds the client only: no API call is made
        assert isinstance(interviewer.llm, GeminiLLMClient)
    finally:
        get_interviewer.cache_clear()  # don't leave a real client cached for other tests
