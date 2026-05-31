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
    "python": "Python",
    "pypi": "PyPI",
    "js": "JavaScript",
    "ts": "TypeScript",
    "npm": "npm",
    "go": "Go",
    "rust": "Rust",
    "cargo": "Cargo",
    "dotnet": ".NET",
    "nuget": "NuGet",
    "docker": "Docker",
    "helm": "Helm",
    "kubernetes": "Kubernetes",
    "githubactions": "GitHub Actions",
    "ruby": "Ruby",
    "php": "PHP",
    "cplusplus": "C++",
    "swift": "Swift",
    "kotlin": "Kotlin",
    "dart": "Dart",
    "perl": "Perl",
    "scala": "Scala",
    "haskell": "Haskell",
    "rubygems": "RubyGems",
    "packagist": "Packagist",
    "generic": "Source",
}

PLATFORM_COLORS: dict[str, str] = {
    "github": "#181717",
    "gitlab": "#FC6D26",
    "bitbucket": "#0052CC",
    "azure": "#0078D7",
    "codeberg": "#2185D0",
    "gitea": "#609926",
    "python": "#3776AB",
    "pypi": "#3775A9",
    "npm": "#CB3837",
    "go": "#00ADD8",
    "rust": "#000000",
    "nuget": "#004880",
    "docker": "#2496ED",
    "githubactions": "#2088FF",
    "ts": "#3178C6",
    "ruby": "#CC342D",
    "php": "#777BB4",
    "dotnet": "#512BD4",
    "cplusplus": "#00599C",
    "swift": "#FA7343",
    "kotlin": "#0095D5",
    "dart": "#0175C2",
    "perl": "#39457E",
    "scala": "#DC322F",
    "haskell": "#5D4F85",
    "rubygems": "#CC342D",
    "packagist": "#F5774D",
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
    "python": "python",
    "pypi": "pypi",
    "npm": "npm",
    "go": "go",
    "rust": "rust",
    "nuget": "nuget",
    "docker": "docker",
    "githubactions": "githubactions",
    "ts": "typescript",
    "ruby": "ruby",
    "php": "php",
    "dotnet": "dotnet",
    "cplusplus": "cplusplus",
    "swift": "swift",
    "kotlin": "kotlin",
    "dart": "dart",
    "perl": "perl",
    "scala": "scala",
    "haskell": "haskell",
    "rubygems": "rubygems",
    "packagist": "packagist",
}

PLATFORM_ICONS: dict[str, str] = {
    "github": "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
    "gitlab": "m23.6004 9.5927-.0337-.0862L20.3.9814a.851.851 0 0 0-.3362-.405.8748.8748 0 0 0-.9997.0539.8748.8748 0 0 0-.29.4399l-2.2055 6.748H7.5375l-2.2057-6.748a.8573.8573 0 0 0-.29-.4412.8748.8748 0 0 0-.9997-.0537.8585.8585 0 0 0-.3362.4049L.4332 9.5015l-.0325.0862a6.0657 6.0657 0 0 0 2.0119 7.0105l.0113.0087.03.0213 4.976 3.7264 2.462 1.8633 1.4995 1.1321a1.0085 1.0085 0 0 0 1.2197 0l1.4995-1.1321 2.4619-1.8633 5.006-3.7489.0125-.01a6.0682 6.0682 0 0 0 2.0094-7.003z",
    "bitbucket": "M.778 1.213a.768.768 0 00-.768.892l3.263 19.81c.084.5.515.868 1.022.873H19.95a.772.772 0 00.77-.646l3.27-20.03a.768.768 0 00-.768-.891zM14.52 15.53H9.522L8.17 8.466h7.561z",
    "azure": "M2 22l6-16h4l6 16h-4l-1-3h-6l-1 3h-4zm5-7h4l-2-6-2 6zm6-9v12h4c3 0 5-2 5-6s-2-6-5-6h-4zm3 3h1c1 0 2 1 2 3s-1 3-2 3h-1v-6zm5-3c-4 0-7 3-7 7s3 7 7 7s7-3 7-7s-3-7-7-7zm0 3c2 0 4 1 4 4s-2 4-4 4s-4-1-4-4s2-4 4-4z",
    "codeberg": "M11.999.747A11.974 11.974 0 0 0 0 12.75c0 2.254.635 4.465 1.833 6.376L11.837 6.19c.072-.092.251-.092.323 0l4.178 5.402h-2.992l.065.239h3.113l.882 1.138h-3.674l.103.374h3.86l.777 1.003h-4.358l.135.483h4.593l.695.894h-5.038l.165.589h5.326l.609.785h-5.717l.182.65h6.038l.562.727h-6.397l.183.65h6.717A12.003 12.003 0 0 0 24 12.75 11.977 11.977 0 0 0 11.999.747zm3.654 19.104.182.65h5.326c.173-.204.353-.433.513-.65zm.385 1.377.18.65h3.563c.233-.198.485-.428.712-.65zm.383 1.377.182.648h1.203c.356-.204.685-.412 1.042-.648zz",
    "gitea": "M4.209 4.603c-.247 0-.525.02-.84.088-.333.07-1.28.283-2.054 1.027C-.403 7.25.035 9.685.089 10.052c.065.446.263 1.687 1.21 2.768 1.749 2.141 5.513 2.092 5.513 2.092s.462 1.103 1.168 2.119c.955 1.263 1.936 2.248 2.89 2.367 2.406 0 7.212-.004 7.212-.004s.458.004 1.08-.394c.535-.324 1.013-.893 1.013-.893s.492-.527 1.18-1.73c.21-.37.385-.729.538-1.068 0 0 2.107-4.471 2.107-8.823-.042-1.318-.367-1.55-.443-1.627-.156-.156-.366-.153-.366-.153s-4.475.252-6.792.306c-.508.011-1.012.023-1.512.027v4.474l-.634-.301c0-1.39-.004-4.17-.004-4.17-1.107.016-3.405-.084-3.405-.084s-5.399-.27-5.987-.324c-.187-.011-.401-.032-.648-.032zm.354 1.832h.111s.271 2.269.6 3.597C5.549 11.147 6.22 13 6.22 13s-.996-.119-1.641-.348c-.99-.324-1.409-.714-1.409-.714s-.73-.511-1.096-1.52C1.444 8.73 2.021 7.7 2.021 7.7s.32-.859 1.47-1.145c.395-.106.863-.12 1.072-.12zm8.33 2.554c.26.003.509.127.509.127l.868.422-.529 1.075a.686.686 0 0 0-.614.359.685.685 0 0 0 .072.756l-.939 1.924a.69.69 0 0 0-.66.527.687.687 0 0 0 .347.763.686.686 0 0 0 .867-.206.688.688 0 0 0-.069-.882l.916-1.874a.667.667 0 0 0 .237-.02.657.657 0 0 0 .271-.137 8.826 8.826 0 0 1 1.016.512.761.761 0 0 1 .286.282c.073.21-.073.569-.073.569-.087.29-.702 1.55-.702 1.55a.692.692 0 0 0-.676.477.681.681 0 1 0 1.157-.252c.073-.141.141-.282.214-.431.19-.397.515-1.16.515-1.16.035-.066.218-.394.103-.814-.095-.435-.48-.638-.48-.638-.467-.301-1.116-.58-1.116-.58s0-.156-.042-.27a.688.688 0 0 0-.148-.241l.516-1.062 2.89 1.401s.48.218.583.619c.073.282-.019.534-.069.657-.24.587-2.1 4.317-2.1 4.317s-.232.554-.748.588a1.065 1.065 0 0 1-.393-.045l-.202-.08-4.31-2.1s-.417-.218-.49-.596c-.083-.31.104-.691.104-.691l2.073-4.272s.183-.37.466-.497a.855.855 0 0 1 .35-.077z",
    "python": "M14.25.18l.9.2.73.26.59.3.45.32.34.34.25.34.16.33.1.3.04.26.02.2-.01.13V8.5l-.05.63-.13.55-.21.46-.26.38-.3.31-.33.25-.35.19-.35.14-.33.1-.3.07-.26.04-.21.02H8.77l-.69.05-.59.14-.5.22-.41.27-.33.32-.27.35-.2.36-.15.37-.1.35-.07.32-.04.27-.02.21v3.06H3.17l-.21-.03-.28-.07-.32-.12-.35-.18-.36-.26-.36-.36-.35-.46-.32-.59-.28-.73-.21-.88-.14-1.05-.05-1.23.06-1.22.16-1.04.24-.87.32-.71.36-.57.4-.44.42-.33.42-.24.4-.16.36-.1.32-.05.24-.01h.16l.06.01h8.16v-.83H6.18l-.01-2.75-.02-.37.05-.34.11-.31.17-.28.25-.26.31-.23.38-.2.44-.18.51-.15.58-.12.64-.1.71-.06.77-.04.84-.02 1.27.05zm-6.3 1.98l-.23.33-.08.41.08.41.23.34.33.22.41.09.41-.09.33-.22.23-.34.08-.41-.08-.41-.23-.33-.33-.22-.41-.09-.41.09zm13.09 3.95l.28.06.32.12.35.18.36.27.36.35.35.47.32.59.28.73.21.88.14 1.04.05 1.23-.06 1.23-.16 1.04-.24.86-.32.71-.36.57-.4.45-.42.33-.42.24-.4.16-.36.09-.32.05-.24.02-.16-.01h-8.22v.82h5.84l.01 2.76.02.36-.05.34-.11.31-.17.29-.25.25-.31.24-.38.2-.44.17-.51.15-.58.13-.64.09-.71.07-.77.04-.84.01-1.27-.04-1.07-.14-.9-.2-.73-.25-.59-.3-.45-.33-.34-.34-.25-.34-.16-.33-.1-.3-.04-.25-.02-.2.01-.13v-5.34l.05-.64.13-.54.21-.46.26-.38.3-.32.33-.24.35-.2.35-.14.33-.1.3-.06.26-.04.21-.02.13-.01h5.84l.69-.05.59-.14.5-.21.41-.28.33-.32.27-.35.2-.36.15-.36.1-.35.07-.32.04-.28.02-.21V6.07h2.09l.14.01zm-6.47 14.25l-.23.33-.08.41.08.41.23.33.33.23.41.08.41-.08.33-.23.23-.33.08-.41-.08-.41-.23-.33-.33-.23-.41-.08-.41.08z",
    "pypi": "M23.922 13.58v3.912L20.55 18.72l-.078.055.052.037 3.45-1.256.026-.036v-3.997l-.053-.036-.025.092z M23.621 5.618l-3.04 1.107v3.912l3.339-1.215V5.509zM23.92 13.457V9.544l-3.336 1.215v3.913zM20.47 14.71V10.8L17.17 12v3.913zM17.034 19.996v-3.912l-3.313 1.206v3.912zM17.17 16.057v3.868l3.314-1.206V14.85l-3.314 1.206zm2.093 1.882c-.367.134-.663-.074-.663-.463s.296-.814.663-.947c.365-.133.662.075.662.464s-.297.814-.662.946z M13.225 9.315l.365-.132-3.285-1.197-3.323 1.21.102.037 3.184 1.16zM20.507 10.664V6.751L17.17 7.965v3.913zM17.058 11.918V8.005l-3.302 1.202v3.912zM13.643 9.246l-3.336 1.215v3.913l3.336-1.215zM6.907 13.165l3.322 1.209v-3.913L6.907 9.252z M10.34 7.873l3.281 1.193V5.198l-3.28-1.193zM20.507 2.715L17.19 3.922v3.913l3.317-1.207zM16.95 3.903L13.724 2.73l-3.269 1.19 3.225 1.174zM15.365 4.606l-1.624.592v3.868l3.317-1.207V3.991l-1.693.615zm-.391 2.778c-.367.134-.662-.074-.662-.464s.295-.813.662-.946c.366-.133.663.074.663.464s-.297.813-.663.946z M10.229 18.41v-3.914l-3.322-1.209V17.2zM13.678 17.182v-3.913l-3.371 1.227v3.913z M13.756 17.154l3.3-1.2V12.04l-3.3 1.2zM13.678 21.217l-3.371 1.227v-3.912h-.078v3.912l-3.322-1.209v-3.913l-.053-.058-.025-.06-3.336-1.21v-3.948l.034.013 3.287 1.196.015-.078-3.261-1.187 3.26-1.187v-.109L3.876 9.62l-.307-.112 3.26-1.188v.877l.079-.055V6.769l3.257 1.185.058-.061L7.084 6.75l-.102-.037 3.24-1.179v-.083L6.854 6.677v.018l-.025.018v1.523L3.44 9.47v.02l-.025.017v4.007l-3.39 1.233v.019L0 14.784v3.995l.025.037 3.4 1.237.008-.006.007.01 3.4 1.238.008-.006.006.01 3.4 1.237.014-.009.012.01 3.45-1.256.026-.037-.078-.027zM3.493 9.563l3.257 1.185-3.257 1.187V9.562zM3.4 19.96L.078 18.752v-3.913l2.361.86.96.349v3.913zm.015-3.99L.335 14.85l-.182-.066 3.262-1.187v2.374zm3.399 5.231l-3.321-1.209v-3.912l3.321 1.209v3.912zM23.791 5.434l-3.21-1.17v2.338zM20.387 2.643l-3.24-1.18-3.27 1.19 3.247 1.182z",
    "npm": "M1.763 0C.786 0 0 .786 0 1.763v20.474C0 23.214.786 24 1.763 24h20.474c.977 0 1.763-.786 1.763-1.763V1.763C24 .786 23.214 0 22.237 0zM5.13 5.323l13.837.019-.009 13.836h-3.464l.01-10.382h-3.456L12.04 19.17H5.113z",
    "go": "M1.811 10.231c-.047 0-.058-.023-.035-.059l.246-.315c.023-.035.081-.058.128-.058h4.172c.046 0 .058.035.035.07l-.199.303c-.023.036-.082.07-.117.07zM.047 11.306c-.047 0-.059-.023-.035-.058l.245-.316c.023-.035.082-.058.129-.058h5.328c.047 0 .07.035.058.07l-.093.28c-.012.047-.058.07-.105.07zm2.828 1.075c-.047 0-.059-.035-.035-.07l.163-.292c.023-.035.07-.07.117-.07h2.337c.047 0 .07.035.07.082l-.023.28c0 .047-.047.082-.082.082zm12.129-2.36c-.736.187-1.239.327-1.963.514-.176.046-.187.058-.34-.117-.174-.199-.303-.327-.548-.444-.737-.362-1.45-.257-2.115.175-.795.514-1.204 1.274-1.192 2.22.011.935.654 1.706 1.577 1.835.795.105 1.46-.175 1.987-.77.105-.13.198-.27.315-.434H10.47c-.245 0-.304-.152-.222-.35.152-.362.432-.97.596-1.274a.315.315 0 01.292-.187h4.253c-.023.316-.023.631-.07.947a4.983 4.983 0 01-.958 2.29c-.841 1.11-1.94 1.8-3.33 1.986-1.145.152-2.209-.07-3.143-.77-.865-.655-1.356-1.52-1.484-2.595-.152-1.274.222-2.419.993-3.424.83-1.086 1.928-1.776 3.272-2.02 1.098-.2 2.15-.07 3.096.571.62.41 1.063.97 1.356 1.648.07.105.023.164-.117.2m3.868 6.461c-1.064-.024-2.034-.328-2.852-1.029a3.665 3.665 0 01-1.262-2.255c-.21-1.32.152-2.489.947-3.529.853-1.122 1.881-1.706 3.272-1.95 1.192-.21 2.314-.095 3.33.595.923.63 1.496 1.484 1.648 2.605.198 1.578-.257 2.863-1.344 3.962-.771.783-1.718 1.273-2.805 1.495-.315.06-.63.07-.934.106zm2.78-4.72c-.011-.153-.011-.27-.034-.387-.21-1.157-1.274-1.81-2.384-1.554-1.087.245-1.788.935-2.045 2.033-.21.912.234 1.835 1.075 2.21.643.28 1.285.244 1.905-.07.923-.48 1.425-1.228 1.484-2.233z",
    "rust": "M23.8346 11.7033l-1.0073-.6236a13.7268 13.7268 0 00-.0283-.2936l.8656-.8069a.3483.3483 0 00-.1154-.578l-1.1066-.414a8.4958 8.4958 0 00-.087-.2856l.6904-.9587a.3462.3462 0 00-.2257-.5446l-1.1663-.1894a9.3574 9.3574 0 00-.1407-.2622l.49-1.0761a.3437.3437 0 00-.0274-.3361.3486.3486 0 00-.3006-.154l-1.1845.0416a6.7444 6.7444 0 00-.1873-.2268l.2723-1.153a.3472.3472 0 00-.417-.4172l-1.1532.2724a14.0183 14.0183 0 00-.2278-.1873l.0415-1.1845a.3442.3442 0 00-.49-.328l-1.076.491c-.0872-.0476-.1742-.0952-.2623-.1407l-.1903-1.1673A.3483.3483 0 0016.256.955l-.9597.6905a8.4867 8.4867 0 00-.2855-.086l-.414-1.1066a.3483.3483 0 00-.5781-.1154l-.8069.8666a9.2936 9.2936 0 00-.2936-.0284L12.2946.1683a.3462.3462 0 00-.5892 0l-.6236 1.0073a13.7383 13.7383 0 00-.2936.0284L9.9803.3374a.3462.3462 0 00-.578.1154l-.4141 1.1065c-.0962.0274-.1903.0567-.2855.086L7.744.955a.3483.3483 0 00-.5447.2258L7.009 2.348a9.3574 9.3574 0 00-.2622.1407l-1.0762-.491a.3462.3462 0 00-.49.328l.0416 1.1845a7.9826 7.9826 0 00-.2278.1873L3.8413 3.425a.3472.3472 0 00-.4171.4171l.2713 1.1531c-.0628.075-.1255.1509-.1863.2268l-1.1845-.0415a.3462.3462 0 00-.328.49l.491 1.0761a9.167 9.167 0 00-.1407.2622l-1.1662.1894a.3483.3483 0 00-.2258.5446l.6904.9587a13.303 13.303 0 00-.087.2855l-1.1065.414a.3483.3483 0 00-.1155.5781l.8656.807a9.2936 9.2936 0 00-.0283.2935l-1.0073.6236a.3442.3442 0 000 .5892l1.0073.6236c.008.0982.0182.1964.0283.2936l-.8656.8079a.3462.3462 0 00.1155.578l1.1065.4141c.0273.0962.0567.1914.087.2855l-.6904.9587a.3452.3452 0 00.2268.5447l1.1662.1893c.0456.088.0922.1751.1408.2622l-.491 1.0762a.3462.3462 0 00.328.49l1.1834-.0415c.0618.0769.1235.1528.1873.2277l-.2713 1.1541a.3462.3462 0 00.4171.4161l1.153-.2713c.075.0638.151.1255.2279.1863l-.0415 1.1845a.3442.3442 0 00.49.327l1.0761-.49c.087.0486.1741.0951.2622.1407l.1903 1.1662a.3483.3483 0 00.5447.2268l.9587-.6904a9.299 9.299 0 00.2855.087l.414 1.1066a.3452.3452 0 00.5781.1154l.8079-.8656c.0972.0111.1954.0203.2936.0294l.6236 1.0073a.3472.3472 0 00.5892 0l.6236-1.0073c.0982-.0091.1964-.0183.2936-.0294l.8069.8656a.3483.3483 0 00.578-.1154l.4141-1.1066a8.4626 8.4626 0 00.2855-.087l.9587.6904a.3452.3452 0 00.5447-.2268l.1903-1.1662c.088-.0456.1751-.0931.2622-.1407l1.0762.49a.3472.3472 0 00.49-.327l-.0415-1.1845a6.7267 6.7267 0 00.2267-.1863l1.1531.2713a.3472.3472 0 00.4171-.416l-.2713-1.1542c.0628-.0749.1255-.1508.1863-.2278l1.1845.0415a.3442.3442 0 00.328-.49l-.49-1.076c.0475-.0872.0951-.1742.1407-.2623l1.1662-.1893a.3483.3483 0 00.2258-.5447l-.6904-.9587.087-.2855 1.1066-.414a.3462.3462 0 00.1154-.5781l-.8656-.8079c.0101-.0972.0202-.1954.0283-.2936l1.0073-.6236a.3442.3442 0 000-.5892zm-6.7413 8.3551a.7138.7138 0 01.2986-1.396.714.714 0 11-.2997 1.396zm-.3422-2.3142a.649.649 0 00-.7715.5l-.3573 1.6685c-1.1035.501-2.3285.7795-3.6193.7795a8.7368 8.7368 0 01-3.6951-.814l-.3574-1.6684a.648.648 0 00-.7714-.499l-1.473.3158a8.7216 8.7216 0 01-.7613-.898h7.1676c.081 0 .1356-.0141.1356-.088v-2.536c0-.074-.0536-.0881-.1356-.0881h-2.0966v-1.6077h2.2677c.2065 0 1.1065.0587 1.394 1.2088.0901.3533.2875 1.5044.4232 1.8729.1346.413.6833 1.2381 1.2685 1.2381h3.5716a.7492.7492 0 00.1296-.0131 8.7874 8.7874 0 01-.8119.9526zM6.8369 20.024a.714.714 0 11-.2997-1.396.714.714 0 01.2997 1.396zM4.1177 8.9972a.7137.7137 0 11-1.304.5791.7137.7137 0 011.304-.579zm-.8352 1.9813l1.5347-.6824a.65.65 0 00.33-.8585l-.3158-.7147h1.2432v5.6025H3.5669a8.7753 8.7753 0 01-.2834-3.348zm6.7343-.5437V8.7836h2.9601c.153 0 1.0792.1772 1.0792.8697 0 .575-.7107.7815-1.2948.7815zm10.7574 1.4862c0 .2187-.008.4363-.0243.651h-.9c-.09 0-.1265.0586-.1265.1477v.413c0 .973-.5487 1.1846-1.0296 1.2382-.4576.0517-.9648-.1913-1.0275-.4717-.2704-1.5186-.7198-1.8436-1.4305-2.4034.8817-.5599 1.799-1.386 1.799-2.4915 0-1.1936-.819-1.9458-1.3769-2.3153-.7825-.5163-1.6491-.6195-1.883-.6195H5.4682a8.7651 8.7651 0 014.907-2.7699l1.0974 1.151a.648.648 0 00.9182.0213l1.227-1.1743a8.7753 8.7753 0 016.0044 4.2762l-.8403 1.8982a.652.652 0 00.33.8585l1.6178.7188c.0283.2875.0425.577.0425.8717zm-9.3006-9.5993a.7128.7128 0 11.984 1.0316.7137.7137 0 01-.984-1.0316zm8.3389 6.71a.7107.7107 0 01.9395-.3625.7137.7137 0 11-.9405.3635z",
    "nuget": "M1.998.342a1.997 1.997 0 1 0 0 3.995 1.997 1.997 0 0 0 0-3.995zm9.18 4.34a6.156 6.156 0 0 0-6.153 6.155v6.667c0 3.4 2.756 6.154 6.154 6.154h6.667c3.4 0 6.154-2.755 6.154-6.154v-6.667a6.154 6.154 0 0 0-6.154-6.155zm-1.477 2.8a2.496 2.496 0 1 1 0 4.993 2.496 2.496 0 0 1 0-4.993zm7.968 6.16a3.996 3.996 0 1 1-.002 7.992 3.996 3.996 0 0 1 .002-7.992z",
    "docker": "M13.983 11.078h2.119a.186.186 0 00.186-.185V9.006a.186.186 0 00-.186-.186h-2.119a.185.185 0 00-.185.185v1.888c0 .102.083.185.185.185m-2.954-5.43h2.118a.186.186 0 00.186-.186V3.574a.186.186 0 00-.186-.185h-2.118a.185.185 0 00-.185.185v1.888c0 .102.082.185.185.185m0 2.716h2.118a.187.187 0 00.186-.186V6.29a.186.186 0 00-.186-.185h-2.118a.185.185 0 00-.185.185v1.887c0 .102.082.185.185.186m-2.93 0h2.12a.186.186 0 00.184-.186V6.29a.185.185 0 00-.185-.185H8.1a.185.185 0 00-.185.185v1.887c0 .102.083.185.185.186m-2.964 0h2.119a.186.186 0 00.185-.186V6.29a.185.185 0 00-.185-.185H5.136a.186.186 0 00-.186.185v1.887c0 .102.084.185.186.186m5.893 2.715h2.118a.186.186 0 00.186-.185V9.006a.186.186 0 00-.186-.186h-2.118a.185.185 0 00-.185.185v1.888c0 .102.082.185.185.185m-2.93 0h2.12a.185.185 0 00.184-.185V9.006a.185.185 0 00-.184-.186h-2.12a.185.185 0 00-.184.185v1.888c0 .102.083.185.185.185m-2.964 0h2.119a.185.185 0 00.185-.185V9.006a.185.185 0 00-.184-.186h-2.12a.186.186 0 00-.186.186v1.887c0 .102.084.185.186.185m-2.92 0h2.12a.185.185 0 00.184-.185V9.006a.185.185 0 00-.184-.186h-2.12a.185.185 0 00-.184.185v1.888c0 .102.082.185.185.185M23.763 9.89c-.065-.051-.672-.51-1.954-.51-.338.001-.676.03-1.01.087-.248-1.7-1.653-2.53-1.716-2.566l-.344-.199-.226.327c-.284.438-.49.922-.612 1.43-.23.97-.09 1.882.403 2.661-.595.332-1.55.413-1.744.42H.751a.751.751 0 00-.75.748 11.376 11.376 0 00.692 4.062c.545 1.428 1.355 2.48 2.41 3.124 1.18.723 3.1 1.137 5.275 1.137.983.003 1.963-.086 2.93-.266a12.248 12.248 0 003.823-1.389c.98-.567 1.86-1.288 2.61-2.136 1.252-1.418 1.998-2.997 2.553-4.4h.221c1.372 0 2.215-.549 2.68-1.009.309-.293.55-.65.707-1.046l.098-.288Z",
    "githubactions": "M10.984 13.836a.5.5 0 0 1-.353-.146l-.745-.743a.5.5 0 1 1 .706-.708l.392.391 1.181-1.18a.5.5 0 0 1 .708.707l-1.535 1.533a.504.504 0 0 1-.354.146zm9.353-.147l1.534-1.532a.5.5 0 0 0-.707-.707l-1.181 1.18-.392-.391a.5.5 0 1 0-.706.708l.746.743a.497.497 0 0 0 .706-.001zM4.527 7.452l2.557-1.585A1 1 0 0 0 7.09 4.17L4.533 2.56A1 1 0 0 0 3 3.406v3.196a1.001 1.001 0 0 0 1.527.85zm2.03-2.436L4 6.602V3.406l2.557 1.61zM24 12.5c0 1.93-1.57 3.5-3.5 3.5a3.503 3.503 0 0 1-3.46-3h-2.08a3.503 3.503 0 0 1-3.46 3 3.502 3.502 0 0 1-3.46-3h-.558c-.972 0-1.85-.399-2.482-1.042V17c0 1.654 1.346 3 3 3h.04c.244-1.693 1.7-3 3.46-3 1.93 0 3.5 1.57 3.5 3.5S13.43 24 11.5 24a3.502 3.502 0 0 1-3.46-3H8c-2.206 0-4-1.794-4-4V9.899A5.008 5.008 0 0 1 0 5c0-2.757 2.243-5 5-5s5 2.243 5 5a5.005 5.005 0 0 1-4.952 4.998A2.482 2.482 0 0 0 7.482 12h.558c.244-1.693 1.7-3 3.46-3a3.502 3.502 0 0 1 3.46 3h2.08a3.503 3.503 0 0 1 3.46-3c1.93 0 3.5 1.57 3.5 3.5zm-15 8c0 1.378 1.122 2.5 2.5 2.5s2.5-1.122 2.5-2.5-1.122-2.5-2.5-2.5S9 19.122 9 20.5zM5 9c2.206 0 4-1.794 4-4S7.206 1 5 1 1 2.794 1 5s1.794 4 4 4zm9 3.5c0-1.378-1.122-2.5-2.5-2.5S9 11.122 9 12.5s1.122 2.5 2.5 2.5 2.5-1.122 2.5-2.5zm9 0c0-1.378-1.122-2.5-2.5-2.5S18 11.122 18 12.5s1.122 2.5 2.5 2.5 2.5-1.122 2.5-2.5zm-13 8a.5.5 0 1 0 1 0 .5.5 0 0 0-1 0zm2 0a.5.5 0 1 0 1 0 .5.5 0 0 0-1 0zm12 0c0 1.93-1.57 3.5-3.5 3.5a3.503 3.503 0 0 1-3.46-3.002c-.007.001-.013.005-.021.005l-.506.017h-.017a.5.5 0 0 1-.016-.999l.506-.017c.018-.002.035.006.052.007A3.503 3.503 0 0 1 20.5 17c1.93 0 3.5 1.57 3.5 3.5zm-1 0c0-1.378-1.122-2.5-2.5-2.5S18 19.122 18 20.5s1.122 2.5 2.5 2.5 2.5-1.122 2.5-2.5z",
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
    elif badge_variant in ("adaptive", "adaptive-reto") and badge_style == "svg":
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
