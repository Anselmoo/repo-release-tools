"""Platform detection and badge generation for source code anchors.

Detects git hosting platforms from repository URLs, provides per-platform
source link URL templates, and generates flat-design SVG badge files in three
visual variants (color, dark, light).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Per-platform source URL templates
# ---------------------------------------------------------------------------

PLATFORM_URL_TEMPLATES: dict[str, str] = {
    "github": "{repo_url}/blob/{ref}/{path}#L{line}",
    "gitlab": "{repo_url}/-/blob/{ref}/{path}#L{line}",
    "bitbucket": "{repo_url}/src/{ref}/{path}#lines-{line}",
    "azure": "{repo_url}?path=/{path}&version=GB{ref}&line={line}",
    "codeberg": "{repo_url}/src/branch/{ref}/{path}#L{line}",
    "gitea": "{repo_url}/src/branch/{ref}/{path}#L{line}",
    "generic": "{repo_url}/blob/{ref}/{path}",
}

# ---------------------------------------------------------------------------
# Platform display names, brand colors, shields.io slugs
# ---------------------------------------------------------------------------

PLATFORM_LABELS: dict[str, str] = {
    "github": "GitHub",
    "gitlab": "GitLab",
    "bitbucket": "Bitbucket",
    "azure": "Azure DevOps",
    "codeberg": "Codeberg",
    "gitea": "Gitea",
    "generic": "Source",
}

PLATFORM_COLORS: dict[str, str] = {
    "github": "#181717",
    "gitlab": "#FC6D26",
    "bitbucket": "#0052CC",
    "azure": "#0078D7",
    "codeberg": "#2185D0",
    "gitea": "#609926",
    "generic": "#555555",
}

# Simple-icons logo identifiers used on shields.io
_SHIELDS_LOGO: dict[str, str] = {
    "github": "github",
    "gitlab": "gitlab",
    "bitbucket": "bitbucket",
    "azure": "azuredevops",
    "codeberg": "codeberg",
    "gitea": "gitea",
}

# ---------------------------------------------------------------------------
# Badge variant color schemes
# ---------------------------------------------------------------------------

# Maps variant name → (bg_color, text_color).
# ``"platform"`` as bg_color means "use PLATFORM_COLORS[platform]".
BADGE_VARIANT_COLORS: dict[str, tuple[str, str]] = {
    "color": ("platform", "#ffffff"),
    "dark": ("#0d1117", "#ffffff"),
    "light": ("#f6f8fa", "#24292e"),
}

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

_PLATFORM_HOST_PATTERNS: tuple[tuple[str, str], ...] = (
    ("github.com", "github"),
    ("gitlab.com", "gitlab"),
    ("bitbucket.org", "bitbucket"),
    ("dev.azure.com", "azure"),
    ("visualstudio.com", "azure"),
    ("codeberg.org", "codeberg"),
    ("gitea.io", "gitea"),
)


def detect_platform(repo_url: str) -> str:
    """Return the platform name for *repo_url*, or ``"generic"`` if unknown.

    Handles self-hosted GitLab/Gitea instances via heuristics:
    - URLs containing ``/gitlab/`` or ``gitlab.`` subdomain → ``"gitlab"``
    - URLs containing ``/gitea/`` or ``gitea.`` subdomain → ``"gitea"``
    """
    if not repo_url:
        return "generic"

    url_lower = repo_url.lower()

    for host_fragment, platform in _PLATFORM_HOST_PATTERNS:
        if host_fragment in url_lower:
            return platform

    # Self-hosted heuristics based on subdomain or path segment
    from urllib.parse import urlparse

    try:
        parsed = urlparse(repo_url)
        host = parsed.hostname or ""
        path = parsed.path or ""
    except ValueError:
        return "generic"

    if host.startswith("gitlab.") or "/gitlab/" in path:
        return "gitlab"
    if host.startswith("gitea.") or "/gitea/" in path:
        return "gitea"

    return "generic"


# ---------------------------------------------------------------------------
# shields.io badge URL
# ---------------------------------------------------------------------------


def shields_badge_url(platform: str, label: str | None = None) -> str:
    """Return a shields.io badge image URL for *platform*."""
    display = label or PLATFORM_LABELS.get(platform, platform.title())
    color = PLATFORM_COLORS.get(platform, PLATFORM_COLORS["generic"]).lstrip("#")
    logo = _SHIELDS_LOGO.get(platform)

    slug = display.replace(" ", "%20")
    url = f"https://img.shields.io/badge/source-{slug}-{color}"
    if logo:
        url += f"?logo={logo}&logoColor=white"
    return url


# ---------------------------------------------------------------------------
# SVG badge generation
# ---------------------------------------------------------------------------

_SVG_TEMPLATE = """\
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img" aria-label="{label}">
  <title>{label}</title>
  <rect width="{width}" height="{height}" rx="3" fill="{bg_color}"/>
  <text x="{cx}" y="{cy}" fill="{text_color}" text-anchor="middle"
        font-family="DejaVu Sans,Verdana,Geneva,sans-serif"
        font-size="{font_size}">{label}</text>
</svg>
"""


def make_badge_svg(
    platform: str,
    *,
    width: int = 88,
    height: int = 20,
    label: str | None = None,
    variant: str = "color",
) -> str:
    """Return an SVG badge string for *platform*.

    Args:
        platform: One of the known platform keys or ``"generic"``.
        width: Badge width in pixels.
        height: Badge height in pixels.
        label: Override display text (defaults to ``PLATFORM_LABELS[platform]``).
        variant: Color scheme — ``"color"`` (brand color), ``"dark"``, or ``"light"``.

    Returns:
        SVG markup as a UTF-8 string (no leading/trailing whitespace).
    """
    display = label or PLATFORM_LABELS.get(platform, platform.title())

    bg_color_spec, text_color = BADGE_VARIANT_COLORS.get(variant, BADGE_VARIANT_COLORS["color"])
    bg_color = (
        PLATFORM_COLORS.get(platform, PLATFORM_COLORS["generic"])
        if bg_color_spec == "platform"
        else bg_color_spec
    )

    cx = width // 2
    cy = int(height * 0.72)
    font_size = max(9, height - 8)

    return _SVG_TEMPLATE.format(
        width=width,
        height=height,
        label=display,
        bg_color=bg_color,
        text_color=text_color,
        cx=cx,
        cy=cy,
        font_size=font_size,
    ).strip()


def get_badge_svg(platform: str, variant: str = "color") -> str:
    """Return SVG content for *platform*/*variant* from bundled package data.

    Falls back to generating via :func:`make_badge_svg` if the asset is not
    found (e.g. in an editable install where assets haven't been written yet).

    Args:
        platform: Platform key (e.g. ``"github"``).
        variant: ``"color"``, ``"dark"``, or ``"light"``.

    Returns:
        SVG markup string.
    """
    from importlib.resources import files

    suffix = f"-{variant}" if variant != "color" else ""
    filename = f"{platform}{suffix}.svg"
    try:
        return (
            files("repo_release_tools.assets.badges").joinpath(filename).read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError, TypeError):
        return make_badge_svg(platform, variant=variant)


# ---------------------------------------------------------------------------
# Badge rendering (markdown / plain text)
# ---------------------------------------------------------------------------


def render_badge(
    platform: str,
    *,
    repo_url: str,
    badge_style: str = "svg",
    badge_assets_dir: str = "docs/assets/badges",
    badge_variant: str = "color",
    label: str | None = None,
    linked: bool = True,
) -> str:
    """Render a platform badge as a Markdown or plain-text string.

    Args:
        platform: Detected or configured platform key.
        repo_url: Repository root URL used as the link target.
        badge_style: One of:
            - ``"svg"`` — local file reference (requires ``rrt docs badges`` to have run)
            - ``"shields"`` — shields.io remote image URL
            - ``"text"`` — plain ``[Label](url)`` Markdown link (or bare label)
        badge_assets_dir: Relative path to the badges directory for ``"svg"`` style.
        badge_variant: SVG variant to reference — ``"color"``, ``"dark"``, or ``"light"``.
        label: Override display text.
        linked: When ``True``, wrap the image/text in a Markdown link.

    Returns:
        Markdown fragment, e.g.
        ``"[![GitHub](docs/assets/badges/github.svg)](https://github.com/…)"``
    """
    display = label or PLATFORM_LABELS.get(platform, platform.title())

    if badge_style == "text":
        if linked and repo_url:
            return f"[{display}]({repo_url})"
        return display

    if badge_style == "shields":
        img_url = shields_badge_url(platform, label=display)
    else:  # "svg"
        suffix = f"-{badge_variant}" if badge_variant != "color" else ""
        img_url = f"{badge_assets_dir.rstrip('/')}/{platform}{suffix}.svg"

    img_md = f"![{display}]({img_url})"
    if linked and repo_url:
        return f"[{img_md}]({repo_url})"
    return img_md
