from astrolens.mcp.gallery_component import _BASE_WIDGET_DOMAINS, _widget_domains


def test_widget_domains_include_configured_public_origin(monkeypatch) -> None:
    monkeypatch.setenv("ASTROLENS_PUBLIC_BASE_URL", "https://astrolens.onrender.com/")

    domains = _widget_domains()

    assert "https://astrolens.onrender.com" in domains
    assert set(_BASE_WIDGET_DOMAINS) <= set(domains)


def test_widget_domains_ignore_invalid_public_origin(monkeypatch) -> None:
    monkeypatch.setenv("ASTROLENS_PUBLIC_BASE_URL", "not-a-url")

    assert _widget_domains() == _BASE_WIDGET_DOMAINS


def test_widget_domains_without_configuration(monkeypatch) -> None:
    monkeypatch.delenv("ASTROLENS_PUBLIC_BASE_URL", raising=False)

    assert _widget_domains() == _BASE_WIDGET_DOMAINS
