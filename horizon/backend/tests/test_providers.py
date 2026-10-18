import os

from app.ai.provider import get_provider


def test_mock_provider_deterministic():
    provider = get_provider()
    assert provider.name == "mock"
    r1 = provider.complete(system="s", user="u", task="classify")
    r2 = provider.complete(system="s", user="u", task="classify")
    assert r1.parsed == r2.parsed
    assert r1.parsed["is_financial_policy"] is True


def test_unknown_provider_raises():
    os.environ["LLM_PROVIDER"] = "nonsense"
    try:
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            get_provider()
            raise AssertionError("应当抛错")
        except ValueError:
            pass
    finally:
        os.environ["LLM_PROVIDER"] = "mock"
        from app.core.config import get_settings

        get_settings.cache_clear()


def test_dashscope_requires_key():
    from app.ai.providers.dashscope import DashScopeProvider

    try:
        DashScopeProvider(api_key="", base_url="https://example.com")
        raise AssertionError("应当抛错")
    except ValueError:
        pass
