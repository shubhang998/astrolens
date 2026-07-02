from astrolens.mcp.gallery_component import (
    _BASE_WIDGET_DOMAINS,
    GALLERY_HTML,
    _widget_domains,
)


def test_widget_renders_facts_panel_and_bounded_media() -> None:
    # Structural guards for the ChatGPT widget: it reads compiled facts,
    # narrative, and credits, and caps the image grid at two.
    for token in (
        "object_facts",
        "why_interesting",
        "collectItems",
        "renderPanel",
        "Keep exploring",
        "suggested_followups",
        "sendFollowup",
        "credit_line",
        ".slice(0, 2)",
    ):
        assert token in GALLERY_HTML, token


def test_widget_is_self_contained_and_url_safe() -> None:
    # CSP forbids external resources; the widget must inline everything and
    # sanitize interpolated URLs.
    assert "safeUrl" in GALLERY_HTML
    assert "about:blank" in GALLERY_HTML
    assert "<script src" not in GALLERY_HTML
    assert 'href="http' not in GALLERY_HTML  # no hardcoded external links


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
