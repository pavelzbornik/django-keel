"""Behavioral tests for the keel-seo feature wiring (ADR-069)."""

from __future__ import annotations


def test_keel_seo_wired_when_enabled(generate):
    """use_keel_seo wires the app, context processor, urls, settings and dependency."""
    project = generate(
        use_keel_seo=True,
        use_programmatic_seo=True,
        frontend="htmx-tailwind",
        frontend_bundling="vite",
    )

    settings = (project / "config/settings/base.py").read_text()
    assert '"keel_seo",' in settings
    assert '"keel_seo.pseo",' in settings
    assert "django.contrib.sitemaps" in settings
    assert "keel_seo.context_processors.seo_defaults" in settings
    assert "SEO_ANALYTICS_UMAMI_ID" in settings

    urls = (project / "config/urls.py").read_text()
    assert "from keel_seo.urls import seo_urlpatterns" in urls
    assert "*seo_urlpatterns," in urls
    assert "PseoSitemap" in urls

    base_html = (project / "templates/base.html").read_text()
    assert "{% load keel_seo %}" in base_html
    assert "{% seo_head with_title=False %}" in base_html
    assert "{% analytics %}" in base_html

    pyproject = (project / "pyproject.toml").read_text()
    assert '"keel-seo[pseo]"' in pyproject
    assert "keel-seo = { workspace = true }" in pyproject


def test_keel_seo_excluded_when_disabled(generate):
    """Without the flag the project keeps its built-in robots/sitemap views."""
    project = generate(use_keel_seo=False)

    settings = (project / "config/settings/base.py").read_text()
    assert "keel_seo" not in settings

    urls = (project / "config/urls.py").read_text()
    assert "keel_seo" not in urls
    assert "from apps.core.views import robots_txt, sitemap" in urls

    pyproject = (project / "pyproject.toml").read_text()
    assert "keel-seo" not in pyproject


def test_programmatic_seo_flag_gates_engine(generate):
    """use_keel_seo without programmatic SEO wires Layer 1/3 but not the pSEO app."""
    project = generate(use_keel_seo=True, use_programmatic_seo=False)

    settings = (project / "config/settings/base.py").read_text()
    assert '"keel_seo",' in settings
    assert '"keel_seo.pseo",' not in settings

    pyproject = (project / "pyproject.toml").read_text()
    assert '"keel-seo",' in pyproject
    assert "[pseo]" not in pyproject
