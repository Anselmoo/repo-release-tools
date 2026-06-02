"""Tests for repo_release_tools.tools.platform."""

from __future__ import annotations

import pytest

from repo_release_tools.tools.platform import (
    _SHIELDS_LOGO,
    ICON_DEFINITIONS,
    KNOWN_LABEL_KEYS,
    LANGUAGE_LABELS,
    PLATFORM_COLORS,
    PLATFORM_LABELS,
    PLATFORM_URL_TEMPLATES,
    REGISTRY_LABELS,
    detect_platform,
    get_badge_svg,
    make_badge_svg,
    render_badge,
    shields_badge_url,
)

# ---------------------------------------------------------------------------
# detect_platform
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/owner/repo", "github"),
        ("https://gitlab.com/owner/repo", "gitlab"),
        ("https://bitbucket.org/owner/repo", "bitbucket"),
        ("https://dev.azure.com/org/proj/_git/repo", "azure"),
        ("https://org.visualstudio.com/proj/_git/repo", "azure"),
        ("https://codeberg.org/owner/repo", "codeberg"),
        ("https://try.gitea.io/owner/repo", "gitea"),
        # Self-hosted GitLab via subdomain
        ("https://gitlab.mycompany.com/owner/repo", "gitlab"),
        # Self-hosted GitLab via path segment
        ("https://vcs.example.com/gitlab/owner/repo", "gitlab"),
        # Self-hosted Gitea via subdomain
        ("https://gitea.mycompany.com/owner/repo", "gitea"),
        # Unknown → generic
        ("https://mygit.example.com/owner/repo", "generic"),
        # Hostname detection should ignore host-like fragments in path/query
        ("https://example.com/github.com/owner/repo?via=gitlab.com", "generic"),
        ("", "generic"),
    ],
)
def test_detect_platform(url: str, expected: str) -> None:
    assert detect_platform(url) == expected


# ---------------------------------------------------------------------------
# PLATFORM_URL_TEMPLATES
# ---------------------------------------------------------------------------


def test_all_platforms_have_templates() -> None:
    all_labels = {**PLATFORM_LABELS, **REGISTRY_LABELS, **LANGUAGE_LABELS}
    for platform in PLATFORM_URL_TEMPLATES:
        assert platform in all_labels, f"{platform!r} has a URL template but no display label"


@pytest.mark.parametrize(
    ("platform", "repo_url", "ref", "path", "line", "expected_fragment"),
    [
        (
            "github",
            "https://github.com/o/r",
            "main",
            "src/foo.py",
            "42",
            "/blob/main/src/foo.py#L42",
        ),
        (
            "gitlab",
            "https://gitlab.com/o/r",
            "main",
            "src/foo.py",
            "1",
            "/-/blob/main/src/foo.py#L1",
        ),
        (
            "bitbucket",
            "https://bitbucket.org/o/r",
            "main",
            "src/foo.py",
            "5",
            "/src/main/src/foo.py#lines-5",
        ),
        (
            "azure",
            "https://dev.azure.com/o/p/_git/r",
            "main",
            "src/foo.py",
            "3",
            "?path=/src/foo.py&version=GBmain&line=3",
        ),
        (
            "codeberg",
            "https://codeberg.org/o/r",
            "main",
            "src/foo.py",
            "7",
            "/src/branch/main/src/foo.py#L7",
        ),
        (
            "gitea",
            "https://gitea.io/o/r",
            "main",
            "src/foo.py",
            "9",
            "/src/branch/main/src/foo.py#L9",
        ),
    ],
)
def test_url_template_expansion(
    platform: str,
    repo_url: str,
    ref: str,
    path: str,
    line: str,
    expected_fragment: str,
) -> None:
    template = PLATFORM_URL_TEMPLATES[platform]
    result = template.format(repo_url=repo_url, ref=ref, path=path, line=line)
    assert expected_fragment in result


# ---------------------------------------------------------------------------
# make_badge_svg
# ---------------------------------------------------------------------------


def test_make_badge_svg_contains_label() -> None:
    svg = make_badge_svg("github")
    assert "GitHub" in svg


def test_make_badge_svg_contains_color() -> None:
    svg = make_badge_svg("github")
    assert PLATFORM_COLORS["github"] in svg


def test_make_badge_svg_is_valid_xml() -> None:
    import xml.etree.ElementTree as ET

    for platform in KNOWN_LABEL_KEYS:
        svg = make_badge_svg(platform)
        ET.fromstring(svg)  # raises if invalid XML


def test_make_badge_svg_custom_label() -> None:
    svg = make_badge_svg("github", label="My Repo")
    assert "My Repo" in svg
    assert "GitHub" not in svg


def test_make_badge_svg_custom_dimensions() -> None:
    svg = make_badge_svg("gitlab", width=120, height=24)
    assert 'width="120"' in svg
    assert 'height="24"' in svg


def test_make_badge_svg_generic() -> None:
    svg = make_badge_svg("generic")
    assert PLATFORM_COLORS["generic"] in svg


def test_make_badge_svg_unknown_platform() -> None:
    svg = make_badge_svg("mygit")
    # Falls back to generic color, title-cases label
    assert PLATFORM_COLORS["generic"] in svg
    assert "Mygit" in svg


def test_make_badge_svg_special_chars_label() -> None:
    import xml.etree.ElementTree as ET

    svg = make_badge_svg("github", label='C&C <repo> "x"')
    ET.fromstring(svg)
    assert "C&amp;C &lt;repo&gt; &quot;x&quot;" in svg


def _expected_icon_category(key: str) -> str:
    if key == "generic":
        return "generic"
    elif key in PLATFORM_LABELS:
        return "hosting"
    elif key in REGISTRY_LABELS:
        return "registry"
    elif key in LANGUAGE_LABELS:
        return "language"
    else:
        return "ecosystem"


def test_icon_definitions_have_non_empty_path_data() -> None:
    assert all(definition.path.strip() for definition in ICON_DEFINITIONS.values())


def test_icon_categories_follow_label_precedence() -> None:
    for key, definition in ICON_DEFINITIONS.items():
        assert definition.category == _expected_icon_category(key)


def test_shields_logo_mapping_for_icon_definition_keys() -> None:
    missing_logo_keys = set(ICON_DEFINITIONS) - set(_SHIELDS_LOGO)
    assert missing_logo_keys == {"cargo", "generic"}


def test_shields_badge_url_logo_param_follows_mapping_exemptions() -> None:
    for key in ICON_DEFINITIONS:
        url = shields_badge_url(key)
        if key in {"cargo", "generic"}:
            assert "logo=" not in url
        else:
            assert "logo=" in url


# ---------------------------------------------------------------------------
# shields_badge_url
# ---------------------------------------------------------------------------


def test_shields_badge_url_github() -> None:
    from urllib.parse import urlparse

    url = shields_badge_url("github")
    assert url.startswith("https://img.shields.io/")
    assert urlparse(url).netloc == "img.shields.io"
    assert "github" in url.lower()


def test_shields_badge_url_no_logo_for_generic() -> None:
    url = shields_badge_url("generic")
    # generic has no logo in _SHIELDS_LOGO → no logo param
    assert "logo=" not in url


def test_shields_badge_url_custom_label() -> None:
    url = shields_badge_url("gitlab", label="My GitLab")
    assert "My%20GitLab" in url or "My_GitLab" in url or "My GitLab" in url.replace("%20", " ")


def test_shields_badge_url_custom_label_special_chars() -> None:
    from urllib.parse import urlparse

    url = shields_badge_url("github", label="C++ #1%")
    assert urlparse(url).netloc == "img.shields.io"
    assert "C%2B%2B%20%231%25" in url


# ---------------------------------------------------------------------------
# render_badge
# ---------------------------------------------------------------------------


def test_render_badge_svg_style() -> None:
    md = render_badge("github", repo_url="https://github.com/o/r", badge_style="svg")
    # Should produce [![GitHub](docs/assets/badges/github.svg)](https://github.com/o/r)
    assert "github.svg" in md
    assert "https://github.com/o/r" in md
    assert md.startswith("[!")


def test_render_badge_shields_style() -> None:
    md = render_badge("gitlab", repo_url="https://gitlab.com/o/r", badge_style="shields")
    assert md.startswith("[![GitLab](https://img.shields.io/")
    assert "https://gitlab.com/o/r" in md


def test_render_badge_text_style_linked() -> None:
    md = render_badge("github", repo_url="https://github.com/o/r", badge_style="text")
    assert md == "[GitHub](https://github.com/o/r)"


def test_render_badge_text_style_unlinked() -> None:
    md = render_badge("github", repo_url="", badge_style="text", linked=False)
    assert md == "GitHub"


def test_render_badge_svg_inline_not_linked() -> None:
    md = render_badge("github", repo_url="https://github.com/o/r", badge_style="svg", linked=False)
    assert md.startswith("![")
    assert "github.svg" in md
    assert "](" in md
    # No outer link wrapper
    assert not md.startswith("[!")


def test_render_badge_custom_assets_dir() -> None:
    md = render_badge(
        "github",
        repo_url="https://github.com/o/r",
        badge_style="svg",
        badge_assets_dir="assets/icons",
    )
    assert "assets/icons/github.svg" in md


def test_render_badge_no_repo_url_text() -> None:
    md = render_badge("github", repo_url="", badge_style="text")
    # No link target → just text
    assert md == "GitHub"


def test_detect_platform_malformed_url() -> None:
    # Malformed netloc that triggers ValueError in urlparse.hostname
    result = detect_platform("http://[::/path")
    assert result == "generic"


# ---------------------------------------------------------------------------
# make_badge_svg — variant support
# ---------------------------------------------------------------------------


def test_make_badge_svg_dark_variant() -> None:
    svg = make_badge_svg("github", variant="dark")
    assert "#0d1117" in svg


def test_make_badge_svg_light_variant() -> None:
    svg = make_badge_svg("github", variant="light")
    assert "#24292e" in svg
    assert "#f6f8fa" in svg


def test_make_badge_svg_unknown_variant_falls_back_to_color() -> None:
    svg = make_badge_svg("github", variant="neon")
    assert PLATFORM_COLORS["github"] in svg


# ---------------------------------------------------------------------------
# render_badge — badge_variant path building
# ---------------------------------------------------------------------------


def test_render_badge_svg_dark_variant_path() -> None:
    md = render_badge(
        "github", repo_url="https://github.com/o/r", badge_style="svg", badge_variant="dark"
    )
    assert "github-dark.svg" in md


def test_render_badge_svg_color_variant_path() -> None:
    md = render_badge(
        "github", repo_url="https://github.com/o/r", badge_style="svg", badge_variant="color"
    )
    assert "github.svg" in md
    assert "github-color.svg" not in md


def test_render_badge_svg_light_variant_path() -> None:
    md = render_badge(
        "github", repo_url="https://github.com/o/r", badge_style="svg", badge_variant="light"
    )
    assert "github-light.svg" in md


# ---------------------------------------------------------------------------
# get_badge_svg
# ---------------------------------------------------------------------------


def test_get_badge_svg_fallback_unknown_platform() -> None:
    svg = get_badge_svg("mygit", "color")
    assert "<svg" in svg
    assert "Mygit" in svg


def test_get_badge_svg_fallback_known_platform() -> None:
    svg = get_badge_svg("github", "dark")
    assert "<svg" in svg


def test_render_badge_adaptive_variant() -> None:
    """adaptive badge_variant produces a <picture> element."""
    html = render_badge(
        "github",
        repo_url="https://github.com/o/r",
        badge_style="svg",
        badge_variant="adaptive",
        badge_assets_dir="docs/assets/badges",
        linked=True,
    )
    assert "<picture>" in html
    assert "github-dark.svg" in html
    assert "github-light.svg" in html
    assert "github.svg" in html
    assert 'href="https://github.com/o/r"' in html


def test_render_badge_adaptive_reto_variant() -> None:
    """adaptive-reto badge_variant uses reto-dark/reto-light SVGs."""
    html = render_badge(
        "github",
        repo_url="https://github.com/o/r",
        badge_style="svg",
        badge_variant="adaptive-reto",
        badge_assets_dir="docs/assets/badges",
        linked=True,
    )
    assert "<picture>" in html
    assert "github-reto-dark.svg" in html
    assert "github-reto-light.svg" in html


def test_render_badge_adaptive_unlinked() -> None:
    """adaptive without repo_url returns just the <picture> element."""
    html = render_badge(
        "github",
        repo_url="",
        badge_style="svg",
        badge_variant="adaptive",
        badge_assets_dir="docs/assets/badges",
        linked=False,
    )
    assert "<picture>" in html
    assert "<a " not in html
