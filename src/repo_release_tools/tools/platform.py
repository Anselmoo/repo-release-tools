"""Platform detection and badge generation for source code anchors.

Detects git hosting platforms from repository URLs, provides per-platform
source link URL templates, and generates flat-design SVG badge files in five
visual variants:

  color      — platform brand color background, white text/icon
  dark       — GitHub-dark (#0d1117) background, white text/icon
  light      — GitHub-light (#f6f8fa) background, dark text/icon
  reto-dark  — Reto dark (#160f0a) background, amber (#ffb36c) text/icon
  reto-light — Reto light (#f5f0e6) background, brown (#7a4d1c) text/icon

Badge variants are rendered via :func:`make_badge_svg` and cached as package
data under ``repo_release_tools.assets.badges``. :func:`get_badge_svg` reads
from package data with a transparent fallback to :func:`make_badge_svg` for
editable installs and development builds.

Platform icon SVG paths — attribution and compliance
=====================================================

github / gitlab / bitbucket / codeberg / gitea
  Source : Simple Icons  <https://simpleicons.org>
           github.com/simple-icons/simple-icons
  License: CC0-1.0 (Creative Commons Zero 1.0 Universal — public domain).
           The SVG path data itself carries no copyright restriction.
  Trademark: Each logo is a registered trademark of its respective owner.
             CC0 covers only the artwork data, not the brand mark.
             Usage must comply with each platform's brand guidelines:
             • GitHub     — https://github.com/logos
             • GitLab     — https://about.gitlab.com/press/press-kit/
             • Bitbucket  — https://www.atlassian.com/company/news/press-kit
             • Codeberg   — https://codeberg.org/Codeberg/Community
             • Gitea      — https://gitea.io
  How to update: copy the <path d="…"> value from the relevant
             Simple Icons SVG file; do not modify the path data.

azure
  Source : Custom "ADO" monogram — not derived from any third-party icon.
           Created specifically for this project to represent Azure DevOps
           without reproducing Microsoft's trademarked Azure / ADO logos.
  License: same as this project (MIT).
  Trademark: "Azure DevOps" and the Azure logo are trademarks of Microsoft.
             See https://www.microsoft.com/trademarks for usage rules.

generic  (the "code chevrons" < > icon)
  Source : Google Material Icons  <https://fonts.google.com/icons>
           github.com/google/material-design-icons
  License: Apache-2.0  <https://www.apache.org/licenses/LICENSE-2.0>
"""

from __future__ import annotations

from html import escape
from urllib.parse import quote, urlparse

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

PLATFORM_ICONS: dict[str, str] = {
    "github": "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
    "gitlab": "m23.6004 9.5927-.0337-.0862L20.3.9814a.851.851 0 0 0-.3362-.405.8748.8748 0 0 0-.9997.0539.8748.8748 0 0 0-.29.4399l-2.2055 6.748H7.5375l-2.2057-6.748a.8573.8573 0 0 0-.29-.4412.8748.8748 0 0 0-.9997-.0537.8585.8585 0 0 0-.3362.4049L.4332 9.5015l-.0325.0862a6.0657 6.0657 0 0 0 2.0119 7.0105l.0113.0087.03.0213 4.976 3.7264 2.462 1.8633 1.4995 1.1321a1.0085 1.0085 0 0 0 1.2197 0l1.4995-1.1321 2.4619-1.8633 5.006-3.7489.0125-.01a6.0682 6.0682 0 0 0 2.0094-7.003z",
    "bitbucket": "M.778 1.213a.768.768 0 00-.768.892l3.263 19.81c.084.5.515.868 1.022.873H19.95a.772.772 0 00.77-.646l3.27-20.03a.768.768 0 00-.768-.891zM14.52 15.53H9.522L8.17 8.466h7.561z",
    "azure": "M2 22l6-16h4l6 16h-4l-1-3h-6l-1 3h-4zm5-7h4l-2-6-2 6zm6-9v12h4c3 0 5-2 5-6s-2-6-5-6h-4zm3 3h1c1 0 2 1 2 3s-1 3-2 3h-1v-6zm5-3c-4 0-7 3-7 7s3 7 7 7s7-3 7-7s-3-7-7-7zm0 3c2 0 4 1 4 4s-2 4-4 4s-4-1-4-4s2-4 4-4z",
    "codeberg": "M11.999.747A11.974 11.974 0 0 0 0 12.75c0 2.254.635 4.465 1.833 6.376L11.837 6.19c.072-.092.251-.092.323 0l4.178 5.402h-2.992l.065.239h3.113l.882 1.138h-3.674l.103.374h3.86l.777 1.003h-4.358l.135.483h4.593l.695.894h-5.038l.165.589h5.326l.609.785h-5.717l.182.65h6.038l.562.727h-6.397l.183.65h6.717A12.003 12.003 0 0 0 24 12.75 11.977 11.977 0 0 0 11.999.747zm3.654 19.104.182.65h5.326c.173-.204.353-.433.513-.65zm.385 1.377.18.65h3.563c.233-.198.485-.428.712-.65zm.383 1.377.182.648h1.203c.356-.204.685-.412 1.042-.648zz",
    "gitea": "M4.209 4.603c-.247 0-.525.02-.84.088-.333.07-1.28.283-2.054 1.027C-.403 7.25.035 9.685.089 10.052c.065.446.263 1.687 1.21 2.768 1.749 2.141 5.513 2.092 5.513 2.092s.462 1.103 1.168 2.119c.955 1.263 1.936 2.248 2.89 2.367 2.406 0 7.212-.004 7.212-.004s.458.004 1.08-.394c.535-.324 1.013-.893 1.013-.893s.492-.527 1.18-1.73c.21-.37.385-.729.538-1.068 0 0 2.107-4.471 2.107-8.823-.042-1.318-.367-1.55-.443-1.627-.156-.156-.366-.153-.366-.153s-4.475.252-6.792.306c-.508.011-1.012.023-1.512.027v4.474l-.634-.301c0-1.39-.004-4.17-.004-4.17-1.107.016-3.405-.084-3.405-.084s-5.399-.27-5.987-.324c-.187-.011-.401-.032-.648-.032zm.354 1.832h.111s.271 2.269.6 3.597C5.549 11.147 6.22 13 6.22 13s-.996-.119-1.641-.348c-.99-.324-1.409-.714-1.409-.714s-.73-.511-1.096-1.52C1.444 8.73 2.021 7.7 2.021 7.7s.32-.859 1.47-1.145c.395-.106.863-.12 1.072-.12zm8.33 2.554c.26.003.509.127.509.127l.868.422-.529 1.075a.686.686 0 0 0-.614.359.685.685 0 0 0 .072.756l-.939 1.924a.69.69 0 0 0-.66.527.687.687 0 0 0 .347.763.686.686 0 0 0 .867-.206.688.688 0 0 0-.069-.882l.916-1.874a.667.667 0 0 0 .237-.02.657.657 0 0 0 .271-.137 8.826 8.826 0 0 1 1.016.512.761.761 0 0 1 .286.282c.073.21-.073.569-.073.569-.087.29-.702 1.55-.702 1.55a.692.692 0 0 0-.676.477.681.681 0 1 0 1.157-.252c.073-.141.141-.282.214-.431.19-.397.515-1.16.515-1.16.035-.066.218-.394.103-.814-.095-.435-.48-.638-.48-.638-.467-.301-1.116-.58-1.116-.58s0-.156-.042-.27a.688.688 0 0 0-.148-.241l.516-1.062 2.89 1.401s.48.218.583.619c.073.282-.019.534-.069.657-.24.587-2.1 4.317-2.1 4.317s-.232.554-.748.588a1.065 1.065 0 0 1-.393-.045l-.202-.08-4.31-2.1s-.417-.218-.49-.596c-.083-.31.104-.691.104-.691l2.073-4.272s.183-.37.466-.497a.855.855 0 0 1 .35-.077z",
    "generic": "M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z",
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
    "reto-dark": ("#160f0a", "#ffb36c"),
    "reto-light": ("#f5f0e6", "#7a4d1c"),
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

    try:
        parsed = urlparse(repo_url)
        host = parsed.hostname or ""
        path = parsed.path or ""
    except ValueError:
        return "generic"

    host_lower = host.lower()
    path_lower = path.lower()
    for host_fragment, platform in _PLATFORM_HOST_PATTERNS:
        if host_lower == host_fragment or host_lower.endswith(f".{host_fragment}"):
            return platform

    # Self-hosted heuristics based on subdomain or path segment
    if host_lower.startswith("gitlab.") or "/gitlab/" in path_lower:
        return "gitlab"
    if host_lower.startswith("gitea.") or "/gitea/" in path_lower:
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

    slug = quote(display, safe="")
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
  {logo_svg}
  <text x="{cx}" y="{cy}" fill="{text_color}" text-anchor="middle"
        font-family="DejaVu Sans,Verdana,Geneva,sans-serif"
        font-size="{font_size}">{label}</text>
</svg>
"""

_LOGO_TEMPLATE = """\
  <g transform="translate({tx}, {ty}) scale({scale})">
    <path fill="{color}" fill-rule="evenodd" d="{path}"/>
  </g>
"""


def make_badge_svg(
    platform: str,
    *,
    width: int = 110,
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
        variant: Color scheme — ``"color"``, ``"dark"``, ``"light"``, ``"reto-dark"``, or ``"reto-light"``.

    Returns:
        SVG markup as a UTF-8 string (no leading/trailing whitespace).
    """
    display = label or PLATFORM_LABELS.get(platform, platform.title())
    label_xml = escape(display, quote=True)

    bg_color_spec, text_color = BADGE_VARIANT_COLORS.get(variant, BADGE_VARIANT_COLORS["color"])
    bg_color = (
        PLATFORM_COLORS.get(platform, PLATFORM_COLORS["generic"])
        if bg_color_spec == "platform"
        else bg_color_spec
    )

    logo_svg = ""
    icon_path = PLATFORM_ICONS.get(platform)
    if icon_path:
        # Simple Icons are 24x24. Scale to fit badge height (e.g. 14px)
        scale = (height - 6) / 24
        tx = 6
        ty = 3
        logo_svg = _LOGO_TEMPLATE.format(
            tx=tx, ty=ty, scale=scale, color=text_color, path=icon_path
        )
        # Shift text to the right if there is a logo
        cx = (width + 20) // 2
    else:
        cx = width // 2

    cy = int(height * 0.72)
    font_size = max(9, height - 8)

    return _SVG_TEMPLATE.format(
        width=width,
        height=height,
        label=label_xml,
        bg_color=bg_color,
        text_color=text_color,
        cx=cx,
        cy=cy,
        font_size=font_size,
        logo_svg=logo_svg,
    ).strip()


def get_badge_svg(platform: str, variant: str = "color") -> str:
    """Return SVG content for *platform*/*variant* from bundled package data.

    Falls back to generating via :func:`make_badge_svg` if the asset is not
    found (e.g. in an editable install where assets haven't been written yet).

    Args:
        platform: Platform key (e.g. ``"github"``).
        variant: ``"color"``, ``"dark"``, ``"light"``, ``"reto-dark"``, or ``"reto-light"``.

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
        badge_variant: SVG variant to reference — ``"color"``, ``"dark"``, ``"light"``, ``"reto-dark"``, ``"reto-light"``, ``"adaptive"``, or ``"adaptive-reto"``.
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
    elif badge_variant in {"adaptive", "adaptive-reto"} and badge_style == "svg":
        # Adaptive mode: render a <picture> element with dark/light variants
        if badge_variant == "adaptive-reto":
            dark_url = f"{badge_assets_dir.rstrip('/')}/{platform}-reto-dark.svg"
            light_url = f"{badge_assets_dir.rstrip('/')}/{platform}-reto-light.svg"
            color_url = f"{badge_assets_dir.rstrip('/')}/{platform}-reto-dark.svg"
        else:
            dark_url = f"{badge_assets_dir.rstrip('/')}/{platform}-dark.svg"
            light_url = f"{badge_assets_dir.rstrip('/')}/{platform}-light.svg"
            color_url = f"{badge_assets_dir.rstrip('/')}/{platform}.svg"

        img_html = (
            f"<picture>\n"
            f'  <source media="(prefers-color-scheme: dark)" srcset="{dark_url}">\n'
            f'  <source media="(prefers-color-scheme: light)" srcset="{light_url}">\n'
            f'  <img alt="{display}" src="{color_url}">\n'
            f"</picture>"
        )
        if linked and repo_url:
            return f'<p><a href="{repo_url}">{img_html}</a></p>'
        return f"<p>{img_html}</p>"
    else:  # "svg"
        suffix = f"-{badge_variant}" if badge_variant != "color" else ""
        img_url = f"{badge_assets_dir.rstrip('/')}/{platform}{suffix}.svg"

    img_md = f"![{display}]({img_url})"
    if linked and repo_url:
        return f"[{img_md}]({repo_url})"
    return img_md
