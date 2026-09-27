"""Per-target version rendering (RRT-VER-1 tier 2): one canonical value, many spellings.

A repository's canonical version is one :class:`~repo_release_tools.version.semver.Version`
(or, for a calendar-versioned group, one
:class:`~repo_release_tools.version.calver.CalVersion`). Different files that record
that version want it spelled differently: a ``pyproject.toml`` wants a SemVer or
PEP 440 string, a ``.gemspec`` wants the RubyGems dot-segment convention, a git tag
wants a ``v``-prefixed SemVer string, and an OCI image tag cannot contain a ``+``.
:func:`render` produces the right spelling for a named format; :func:`parse_rendered`
reads one back.

Supported formats (:data:`FORMATS`):

* ``semver``   -- SemVer 2.0 (``0.1.0-rc.1``). Refuses a post release: SemVer has
  no post-release grammar.
* ``pep440``   -- PEP 440 (``0.1.0rc1``). Refuses a build/local segment, since this
  format exists for PyPI-publishable targets and PyPI rejects local versions.
* ``python``   -- the default for ``pep621`` and ``python_version`` targets. A final
  or ``alpha``/``beta``/``rc`` version keeps its SemVer spelling (``0.1.0-rc.1``),
  which PEP 440 normalises to the same version, so existing output is unchanged. A
  dev or post release switches to the PEP 440 spelling (``0.1.1.dev0``,
  ``0.1.0.post1``), because the SemVer dev spelling ``0.1.1-0.dev.0`` normalises to
  ``0.1.1.post0.dev0`` in PEP 440 and would sort after the final release.
  A dev or post release gets the ``pep440`` refusals; a ``pep621`` target also
  keeps its own check against local segments.
* ``rubygems`` -- the RubyGems dot-segment convention (``0.1.0.rc.1``,
  ``0.1.0.alpha.1.dev.2``, ``0.1.0.1`` for a post release). Refuses an opaque
  pre-release label and a build/local segment, neither of which RubyGems spells.
* ``go-tag``   -- ``"v"`` followed by the SemVer spelling (``v0.1.0-rc.1``); same
  refusals as ``semver``.
* ``oci-tag``  -- the SemVer spelling with ``+`` replaced by ``-``, because an OCI
  image tag cannot contain ``+``; same refusals as ``semver``. This substitution is
  lossy for a build segment (:meth:`parse_rendered` does not invert it), so
  round-tripping is only guaranteed for a version without one.
* ``calver``   -- accepted only for a :class:`CalVersion`; refused for a
  :class:`Version`, which never carries calendar semantics.

A :class:`CalVersion` has no pre-release, dev, post or build segment, so it renders
the same way -- its own ``str()`` -- in every format except ``go-tag`` (``v`` prefix).

Caveats:

* Every refusal raises :class:`UnrepresentableVersionError`, naming the format and
  the version, and points at ``post_policy`` when a post release is the cause.
* :func:`default_format_for_kind` returns ``"python"`` for ``pep621`` and
  ``python_version``, ``"rubygems"`` for ``gemspec`` and ``"semver"`` for every
  other kind. For finals and channel pre-releases each default writes exactly the
  string it wrote before tier 2, so an existing config's output stays
  byte-identical. Set ``format = "pep440"`` on a target to always use PEP 440
  spelling.

Related docs:

* RRT-VER-1 (issue #259), tier 2.
"""

from __future__ import annotations

import re

from repo_release_tools.version.calver import CalVersion
from repo_release_tools.version.semver import Version

FORMATS: tuple[str, ...] = (
    "semver",
    "pep440",
    "python",
    "rubygems",
    "go-tag",
    "oci-tag",
    "calver",
)
"""Every format :func:`render` accepts, in documentation order."""

# Target kinds that hold a Python (PEP 440) version and default to "python".
_PYTHON_KINDS = frozenset({"pep621", "python_version"})

# Canonical RubyGems channel spelling — same names as the canonical Version
# channel, unlike PEP 440's abbreviated "a"/"b".
_RUBYGEMS_CHANNELS = ("alpha", "beta", "rc")

# `major.minor.patch.<channel>.<number>.dev.<dev>` — a dev release of a channel.
_RUBYGEMS_CHANNEL_DEV_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"\.(?P<channel>alpha|beta|rc)\.(?P<number>0|[1-9]\d*)\.dev\.(?P<dev>0|[1-9]\d*)$",
)
# `major.minor.patch.a.dev.<dev>` — a dev release of the final release.
_RUBYGEMS_FINAL_DEV_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)\.a\.dev\.(?P<dev>0|[1-9]\d*)$",
)
# `major.minor.patch.<channel>.<number>` — a channel pre-release.
_RUBYGEMS_CHANNEL_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"\.(?P<channel>alpha|beta|rc)\.(?P<number>0|[1-9]\d*)$",
)
# `major.minor.patch.<post>` — a post release (a plain trailing numeric segment).
_RUBYGEMS_POST_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)\.(?P<post>[1-9]\d*)$",
)
# `major.minor.patch` — a final release.
_RUBYGEMS_FINAL_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)$",
)


class UnrepresentableVersionError(ValueError):
    """A canonical version has no spelling in the requested format.

    The message names both the format and the version, and, for a post release,
    points at ``post_policy`` -- the config knob that resolves the conflict by
    converting the bump to a patch release instead.
    """


def default_format_for_kind(kind: str | None) -> str:
    """Return the format an unconfigured target of *kind* renders with.

    ``None`` covers ``pattern`` and ``section``/``field`` targets. ``pep621`` and
    ``python_version`` default to ``"python"``, ``gemspec`` to ``"rubygems"``,
    every other kind to ``"semver"``. Each default writes the string the target
    has always received for a final or channel pre-release.
    """
    if kind in _PYTHON_KINDS:
        return "python"
    if kind == "gemspec":
        return "rubygems"
    return "semver"


def render(version: Version | CalVersion, fmt: str) -> str:
    """Render *version* in *fmt*.

    Raises :class:`UnrepresentableVersionError` when *version* has no spelling
    in *fmt* (a post release rendered as ``semver``/``go-tag``/``oci-tag``, a
    build segment rendered as ``pep440``/``rubygems``, an opaque pre-release
    label rendered as ``rubygems``, or any :class:`Version` rendered as
    ``calver``). Raises :class:`ValueError` for an *fmt* outside :data:`FORMATS`.
    """
    if fmt not in FORMATS:
        allowed = ", ".join(repr(f) for f in FORMATS)
        raise ValueError(f"Unknown version format {fmt!r}; expected one of {allowed}.")
    if isinstance(version, CalVersion):
        return _render_calver(version, fmt)
    return _render_version(version, fmt)


def _render_calver(version: CalVersion, fmt: str) -> str:
    """Render a :class:`CalVersion`: identical in every format but ``go-tag``."""
    text = str(version)
    if fmt == "go-tag":
        return f"v{text}"
    return text


def _render_version(version: Version, fmt: str) -> str:
    """Render a :class:`Version` in *fmt* (dispatch table for :func:`render`)."""
    if fmt == "calver":
        raise UnrepresentableVersionError(
            f"Cannot render {version} as calver: it is a SemVer/PEP 440 version, "
            "not a calendar version.",
        )
    if fmt == "semver":
        return _render_semver(version, fmt)
    if fmt == "go-tag":
        return f"v{_render_semver(version, fmt)}"
    if fmt == "oci-tag":
        return _render_semver(version, fmt).replace("+", "-")
    if fmt == "pep440":
        return _render_pep440(version)
    if fmt == "python":
        return _render_python(version)
    return _render_rubygems(version)


def _render_semver(version: Version, fmt: str) -> str:
    """Return the SemVer spelling, refusing a post release.

    *fmt* is the caller-facing format name (``"semver"``, ``"go-tag"`` or
    ``"oci-tag"``), named in the refusal so the error matches what was asked for.
    """
    if version.post is not None:
        raise UnrepresentableVersionError(
            f"Cannot render {version} as {fmt}: post releases have no SemVer "
            'spelling. Set post_policy = "patch" in [tool.rrt] to fold a post '
            "bump into a patch release, or remove this target from the group.",
        )
    # str(Version) only falls back to the PEP 440 spelling for a post release,
    # ruled out above, so this is always the genuine SemVer spelling.
    return str(version)


def _render_pep440(version: Version) -> str:
    """Return the PEP 440 spelling, refusing a build/local segment."""
    if version.build is not None:
        raise UnrepresentableVersionError(
            f"Cannot render {version} as pep440: a local-version segment "
            "('+...') is not PyPI-publishable PEP 440. Remove it, or use a "
            "target format other than pep440.",
        )
    try:
        return version.to_pep440()
    except ValueError as exc:
        raise UnrepresentableVersionError(f"Cannot render {version} as pep440: {exc}") from exc


def _render_python(version: Version) -> str:
    """Return the SemVer spelling where PEP 440 reads it as the same version.

    A final or channel pre-release keeps the SemVer spelling, which is what a
    Python target has always received. A dev or post release uses the PEP 440
    spelling, since its SemVer form has no equivalent PEP 440 reading.
    """
    if version.dev is None and version.post is None:
        return str(version)
    return _render_pep440(version)


def _render_rubygems(version: Version) -> str:
    """Return the RubyGems dot-segment spelling.

    ``major.minor.patch`` for a final release, ``...a.dev.N`` for a dev release
    of the final, ``...<channel>.N[.dev.M]`` for a channel pre-release (its own
    ``M.dev`` release included), and ``...N`` for a post release -- a plain
    trailing numeric segment, RubyGems having no ``post`` keyword.
    """
    if version.build is not None:
        raise UnrepresentableVersionError(
            f"Cannot render {version} as rubygems: a build/local segment "
            "('+...') has no RubyGems spelling. Remove it, or use a target "
            "format other than rubygems.",
        )
    base = f"{version.major}.{version.minor}.{version.patch}"
    if version.post is not None:
        base = f"{base}.{version.post}"
        if version.dev is not None:
            base = f"{base}.dev.{version.dev}"
        return base
    if version.pre is None:
        if version.dev is not None:
            return f"{base}.a.dev.{version.dev}"
        return base
    channel = version.pre_channel
    if channel is None:
        raise UnrepresentableVersionError(
            f"Cannot render {version} as rubygems: the opaque pre-release label "
            f"{version.pre!r} has no RubyGems spelling; only alpha.N, beta.N and "
            "rc.N do.",
        )
    base = f"{base}.{channel}.{version.pre_number}"
    if version.dev is not None:
        base = f"{base}.dev.{version.dev}"
    return base


def parse_rendered(text: str, fmt: str) -> Version:
    """Parse *text*, written by :func:`render` in *fmt*, back into a :class:`Version`.

    The round trip ``parse_rendered(render(v, fmt), fmt) == v`` holds for every
    *v* representable in *fmt* (RRT-VER-1 I1), except that ``oci-tag`` does not
    invert its ``+`` -> ``-`` substitution: it round-trips only a version
    without a build segment.

    Raises :class:`ValueError` for *fmt* not in :data:`FORMATS`, for
    ``"calver"`` (no :class:`Version` renders as one), and for *text* that does
    not match *fmt*'s grammar.
    """
    if fmt not in FORMATS:
        allowed = ", ".join(repr(f) for f in FORMATS)
        raise ValueError(f"Unknown version format {fmt!r}; expected one of {allowed}.")
    if fmt == "semver":
        return Version.parse(text, spelling="semver")
    if fmt == "pep440":
        return Version.parse(text, spelling="pep440")
    if fmt == "python":
        return Version.parse(text, spelling="any")
    if fmt == "go-tag":
        if not text.startswith("v"):
            raise ValueError(f"Invalid go-tag {text!r}: expected a 'v' prefix.")
        return Version.parse(text[1:], spelling="semver")
    if fmt == "oci-tag":
        return Version.parse(text, spelling="semver")
    if fmt == "calver":
        raise ValueError("No Version renders as calver, so none parses back from one.")
    return _parse_rubygems(text)


def _parse_rubygems(text: str) -> Version:
    """Parse a RubyGems-spelled version string back into a :class:`Version`."""
    if m := _RUBYGEMS_CHANNEL_DEV_RE.match(text):
        return Version(
            int(m.group("major")),
            int(m.group("minor")),
            int(m.group("patch")),
            pre=f"{m.group('channel')}.{m.group('number')}",
            dev=int(m.group("dev")),
        )
    if m := _RUBYGEMS_FINAL_DEV_RE.match(text):
        return Version(
            int(m.group("major")),
            int(m.group("minor")),
            int(m.group("patch")),
            dev=int(m.group("dev")),
        )
    if m := _RUBYGEMS_CHANNEL_RE.match(text):
        return Version(
            int(m.group("major")),
            int(m.group("minor")),
            int(m.group("patch")),
            pre=f"{m.group('channel')}.{m.group('number')}",
        )
    if m := _RUBYGEMS_POST_RE.match(text):
        return Version(
            int(m.group("major")),
            int(m.group("minor")),
            int(m.group("patch")),
            post=int(m.group("post")),
        )
    if m := _RUBYGEMS_FINAL_RE.match(text):
        return Version(int(m.group("major")), int(m.group("minor")), int(m.group("patch")))
    raise ValueError(f"Invalid rubygems version: {text!r}")


__all__ = [
    "FORMATS",
    "UnrepresentableVersionError",
    "default_format_for_kind",
    "parse_rendered",
    "render",
]
