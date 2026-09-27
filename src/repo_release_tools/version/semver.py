"""Canonical version model (RRT-VER-1 §1) with SemVer and PEP 440 spellings.

:class:`Version` is one structured value -- ``release`` (``major.minor.patch``),
``pre``, ``post``, ``dev`` and ``local`` (stored as ``build``) -- that both the
SemVer 2.0 and the PEP 440 spelling of a version parse to. ``0.1.0.dev1`` and
``0.1.0-0.dev.1`` are the same value, as are ``0.1.0a1.dev2`` and
``0.1.0-alpha.0.dev.2``, ``0.1.0rc1`` and ``0.1.0-rc.1``, and ``0.1.0.post1`` and
``0.1.0-post.1``.

SemVer spelling (RRT-VER-1 §2 semver column):

* ``M.m.p-0.dev.N``            -- dev release of ``M.m.p``
* ``M.m.p-<ch>.<K>.dev.N``     -- dev release of pre-release ``<ch>.<K+1>``
  (``ch`` is ``alpha``, ``beta`` or ``rc``)
* ``M.m.p-post.N``             -- post release ``N`` (``N >= 1``)
* any other label              -- an opaque SemVer pre-release label, kept verbatim
  with SemVer 2.0 section 11 precedence (``1.0.0-alpha``, ``1.0.0-dev.1``)

PEP 440 spellings are read through the grammar in
:mod:`repo_release_tools.version.pep440`: the channel normalises
(``a``/``alpha`` -> ``alpha``, ``b``/``beta`` -> ``beta``,
``c``/``rc``/``pre``/``preview`` -> ``rc``), ``.postN``/``-N`` maps to ``post`` and
``.devN`` to ``dev``. The local segment becomes ``build``, lowercased with ``-`` and
``_`` turned into ``.``.

Order (:meth:`Version.sort_key`) is SemVer precedence of the canonical SemVer
spelling, extended by a post-release key, and agrees with ``packaging.version``
for every canonical value: ``dev < pre-dev < pre < final < post-dev < post``.

Caveats:

* PEP 440 needs exactly three release components with no leading zeros and no
  epoch other than ``0``; ``1.0``, ``1.0.0.0``, ``01.2.0`` and ``1!1.0.0`` raise.
* A PEP 440 pre-release number of ``0`` (or none, as in ``1.0.0a``) becomes the
  opaque label ``<channel>.0``. It keeps its order but cannot carry a dev
  release, so ``1.0.0a0.dev1`` raises.
* A post release cannot follow a pre-release, and its number must be ``>= 1``
  (``1.0.0rc1.post1`` and ``1.0.0.post0`` raise).
* SemVer cannot express a post release, so ``str()`` of one returns its PEP 440
  spelling; :meth:`Version.to_pep440` raises for an opaque label such as
  ``dev.1`` that PEP 440 cannot express.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from repo_release_tools.version.pep440 import _PEP440_RE

SEMVER_PARTS = 3

# Matches MAJOR.MINOR.PATCH[-pre][+build] per semver 2.0.
# Pre-release: optional -alpha, -alpha.1, -beta.2, -rc.3, etc.
# Build metadata: optional +build.123
_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*))?$"
)

# Channel names accepted as bump kinds by Version.bump().
PRE_RELEASE_CHANNELS = ("alpha", "beta", "rc")

# Decision D-1: which core a pre-release channel targets when started from a FINAL
# version. "auto" derives the level from Conventional Commits and must be resolved to
# one of the other three before reaching Version.bump(). Single source of truth for
# the config model, the CLI --base flag and the MCP base parameter.
PRERELEASE_BASES = ("patch", "minor", "major", "auto")
DEFAULT_PRERELEASE_BASE = "patch"

# The bases Version.bump() applies directly (everything but "auto").
_CONCRETE_PRERELEASE_BASES = ("patch", "minor", "major")

# Accepted values of Version.parse(spelling=...).
VERSION_SPELLINGS = ("any", "semver", "pep440")

# A canonical channel pre-release label: <channel>.<N>, N >= 1.
_CHANNEL_PRE_RE = re.compile(r"^(?P<channel>alpha|beta|rc)\.(?P<number>[1-9]\d*)$")

# The canonical RRT-VER-1 SemVer encodings of dev and post inside a pre-release label.
_DEV_ONLY_LABEL_RE = re.compile(r"^0\.dev\.(?P<dev>0|[1-9]\d*)$")
_CHANNEL_DEV_LABEL_RE = re.compile(
    r"^(?P<channel>alpha|beta|rc)\.(?P<before>0|[1-9]\d*)\.dev\.(?P<dev>0|[1-9]\d*)$"
)
_POST_LABEL_RE = re.compile(r"^post\.(?P<post>[1-9]\d*)$")

# PEP 440 pre-release spellings -> canonical channel.
_PEP440_CHANNELS = {
    "a": "alpha",
    "alpha": "alpha",
    "b": "beta",
    "beta": "beta",
    "c": "rc",
    "rc": "rc",
    "pre": "rc",
    "preview": "rc",
}

# Canonical channel -> PEP 440 pre-release letter.
_PEP440_LETTERS = {"alpha": "a", "beta": "b", "rc": "rc"}

# An opaque label PEP 440 can still spell: a channel with pre-release number 0.
_ZERO_CHANNEL_PRE_RE = re.compile(r"^(?P<channel>alpha|beta|rc)\.0$")

# A PEP 440 release component with a leading zero (01, 007).
_LEADING_ZERO_RE = re.compile(r"^0\d")

# A lowercase PEP 440 local segment in canonical (dot-separated) form.
_PEP440_LOCAL_RE = re.compile(r"^[a-z0-9]+(?:\.[a-z0-9]+)*$")

# One pre-release identifier as a precedence key: (kind, numeric value, text).
# kind 0 = numeric identifier, kind 1 = alphanumeric identifier.
PreReleaseIdentifierKey = tuple[int, int, str]

# Post-release precedence key: (post number or 0, 0 for post-dev else 1, dev number or 0).
PostKey = tuple[int, int, int]

# Full precedence key: (major, minor, patch, stable flag, pre-release identifier keys,
# post key).
SortKey = tuple[int, int, int, int, tuple[PreReleaseIdentifierKey, ...], PostKey]

# The post key of every version without a post release.
NO_POST_KEY: PostKey = (0, 1, 0)


@dataclass(frozen=True)
class Version:
    """Canonical RRT-VER-1 version: release, pre, post, dev and local (``build``).

    ``pre`` is either a canonical channel label (``alpha.N``, ``beta.N``, ``rc.N``
    with ``N >= 1``) or an opaque SemVer label kept verbatim. ``post`` (``>= 1``)
    and ``dev`` (``>= 0``) are optional numbers; ``build`` holds SemVer build
    metadata, which is the same slot as the PEP 440 local segment (:attr:`local`).

    The constructor canonicalises the RRT-VER-1 SemVer encodings passed as
    ``pre``: ``Version(0, 1, 0, pre="0.dev.1") == Version(0, 1, 0, dev=1)``.
    It raises :class:`ValueError` for an impossible combination: ``dev`` on an
    opaque label, ``post`` on a pre-release, ``post < 1`` or ``dev < 0``.

    Equality (``==``) is structural: it comes from the dataclass and compares every
    field, including ``build``. Ordering (``<``, ``<=``, ``>``, ``>=``) follows
    :meth:`sort_key` and ignores build metadata, so ``1.0.0+a`` and ``1.0.0+b`` are
    neither ``<`` nor ``>`` each other yet not ``==``.
    """

    major: int
    minor: int
    patch: int
    pre: str | None = field(default=None)
    build: str | None = field(default=None)
    post: int | None = field(default=None)
    dev: int | None = field(default=None)

    def __post_init__(self) -> None:
        """Canonicalise SemVer dev/post encodings in ``pre`` and validate the fields."""
        if self.pre is not None:
            self._canonicalise_pre_label(self.pre)
        if self.post is not None and self.post < 1:
            raise ValueError(f"post release number must be >= 1, got {self.post}")
        if self.dev is not None and self.dev < 0:
            raise ValueError(f"dev release number must be >= 0, got {self.dev}")
        if self.post is not None and self.pre is not None:
            raise ValueError(
                f"post release {self.post} cannot follow pre-release {self.pre!r}; "
                "a post release only follows a final release"
            )
        if self.dev is not None and self.pre is not None and self.pre_channel is None:
            raise ValueError(
                f"dev release {self.dev} cannot follow the opaque pre-release label "
                f"{self.pre!r}; only alpha.N, beta.N and rc.N (N >= 1) carry a dev release"
            )
        if self.post is not None and self.build is not None:
            if _PEP440_LOCAL_RE.match(self.build) is None:
                raise ValueError(
                    f"build {self.build!r} of a post release must be a lowercase PEP 440 "
                    "local segment, because a post release is spelled in PEP 440"
                )

    def _canonicalise_pre_label(self, pre: str) -> None:
        """Move a canonical SemVer dev/post encoding out of ``pre`` into its fields."""
        if m := _DEV_ONLY_LABEL_RE.match(pre):
            new_pre, dev, post = None, int(m.group("dev")), None
        elif m := _CHANNEL_DEV_LABEL_RE.match(pre):
            new_pre = f"{m.group('channel')}.{int(m.group('before')) + 1}"
            dev, post = int(m.group("dev")), None
        elif m := _POST_LABEL_RE.match(pre):
            new_pre, dev, post = None, None, int(m.group("post"))
        else:
            return
        if self.dev is not None or self.post is not None:
            raise ValueError(
                f"pre-release label {pre!r} already encodes a dev or post release; "
                "give dev and post either in the label or as fields, not both"
            )
        object.__setattr__(self, "pre", new_pre)
        object.__setattr__(self, "dev", dev)
        object.__setattr__(self, "post", post)

    @classmethod
    def parse(cls, raw: str, *, spelling: str = "any") -> Version:
        """Parse a SemVer or PEP 440 version string into a canonical :class:`Version`.

        *spelling* picks the grammar: ``"semver"`` reads only
        ``MAJOR.MINOR.PATCH[-pre][+build]``, ``"pep440"`` only PEP 440, and
        ``"any"`` (the default) tries SemVer first and falls back to PEP 440. A
        failure raises :class:`ValueError` whose message starts with
        ``Invalid semver: '<raw>'``.
        """
        if spelling not in VERSION_SPELLINGS:
            allowed = ", ".join(repr(s) for s in VERSION_SPELLINGS)
            raise ValueError(f"Invalid version spelling {spelling!r}; expected one of {allowed}.")
        text = raw.strip()
        expected = {
            "any": "SemVer MAJOR.MINOR.PATCH[-pre][+build] or PEP 440",
            "semver": "SemVer MAJOR.MINOR.PATCH[-pre][+build]",
            "pep440": "PEP 440",
        }[spelling]
        prefix = f"Invalid semver: {raw!r} (expected {expected})"
        semver_match = _SEMVER_RE.match(text) if spelling != "pep440" else None
        if semver_match is not None:
            try:
                return cls(
                    int(semver_match.group("major")),
                    int(semver_match.group("minor")),
                    int(semver_match.group("patch")),
                    pre=semver_match.group("pre"),
                    build=semver_match.group("build"),
                )
            except ValueError as exc:
                if spelling == "semver":
                    raise ValueError(f"{prefix}: {exc}") from None
                # "any": the PEP 440 reading may still be valid (it lowercases local).
        pep440_match = _PEP440_RE.match(text) if spelling != "semver" else None
        if pep440_match is None:
            raise ValueError(prefix)
        try:
            return cls._from_pep440_match(text, pep440_match)
        except ValueError as exc:
            raise ValueError(f"{prefix}: {exc}") from None

    @classmethod
    def _from_pep440_match(cls, text: str, m: re.Match[str]) -> Version:
        """Build a :class:`Version` from a PEP 440 grammar match; ValueError names why not."""
        if text[:1] in ("v", "V"):
            raise ValueError("a 'v' prefix is not part of the version")
        if m.group("epoch") is not None and int(m.group("epoch")) != 0:
            raise ValueError("a non-zero epoch is not supported")
        release = m.group("release").split(".")
        if len(release) != SEMVER_PARTS:
            raise ValueError("exactly three release components are required")
        if any(_LEADING_ZERO_RE.match(part) for part in release):
            raise ValueError("a release component must not have a leading zero")
        pre: str | None = None
        if m.group("pre_l") is not None:
            channel = _PEP440_CHANNELS[m.group("pre_l").lower()]
            pre = f"{channel}.{int(m.group('pre_n') or 0)}"
        post: int | None = None
        if m.group("post") is not None:
            post = int(m.group("post_n1") or m.group("post_n2") or 0)
        dev = int(m.group("dev_n") or 0) if m.group("dev") is not None else None
        local = m.group("local")
        build = re.sub(r"[-_]", ".", local.lower()) if local is not None else None
        major, minor, patch = (int(part) for part in release)
        return cls(major, minor, patch, pre=pre, build=build, post=post, dev=dev)

    @property
    def release(self) -> tuple[int, int, int]:
        """Return the release segment ``(major, minor, patch)``."""
        return (self.major, self.minor, self.patch)

    @property
    def local(self) -> str | None:
        """Return the local segment; an alias of :attr:`build` (one shared slot)."""
        return self.build

    @property
    def pre_channel(self) -> str | None:
        """Return ``alpha``, ``beta`` or ``rc`` for a canonical channel label, else None."""
        m = _CHANNEL_PRE_RE.match(self.pre) if self.pre is not None else None
        return m.group("channel") if m else None

    @property
    def pre_number(self) -> int | None:
        """Return ``N`` of a canonical ``<channel>.N`` label, else None (opaque or none)."""
        m = _CHANNEL_PRE_RE.match(self.pre) if self.pre is not None else None
        return int(m.group("number")) if m else None

    def bump(self, kind: str, *, base: str = DEFAULT_PRERELEASE_BASE) -> Version:
        """Return a new :class:`Version` bumped by *kind*.

        Accepted kinds:
        - ``major``, ``minor``, ``patch`` — standard semver increments (clears pre/build).
          When the version is already a pre-release whose trailing components are at
          the target boundary (e.g. ``2.0.0-beta.2`` bumping ``major``), this finalizes
          the pre-release in place instead of skipping past it -- the same rule
          node-semver's ``inc()`` uses.
        - ``release`` — finalize the current pre-release to its stable target version,
          unconditionally (requires the version to already carry a pre-release identifier)
        - ``pre-release`` — increment the numeric suffix of the current pre-release label
          (requires the version to already carry a pre-release identifier). On a dev
          release of a channel (``1.0.1rc1.dev2``) this drops the dev number instead of
          incrementing it, landing on the channel release itself (``1.0.1rc1``) -- a dev
          release only ever precedes the release it is a dev release *of*.
        - ``alpha``, ``beta``, ``rc`` — start or advance a named pre-release channel
        - ``dev`` — start or advance a dev release (RRT-VER-1 T1.3):

          * on a FINAL version, bumps the core by *base* (default ``patch``) and starts
            ``dev0`` there (``1.0.0`` -> ``1.0.1.dev0``)
          * on any existing dev release (of a final core, a channel, or -- via
            ``pre-release``/``release`` first -- otherwise), advances the dev number
            (``1.0.1.dev0`` -> ``1.0.1.dev1``; ``1.0.1rc1.dev2`` -> ``1.0.1rc1.dev3``)
          * on a channel pre-release that is not itself a dev release, starts a dev
            release of the *next* pre-release number (``1.0.1rc1`` -> ``1.0.1rc2.dev0``)
          * on a post release, bumps the core by ``patch`` and starts ``dev0`` there
            (``1.0.1.post1`` -> ``1.0.2.dev0``)
        - ``post`` — start or advance a post release (RRT-VER-1 T1.3): ``.post1`` on a
          FINAL or post version, incrementing on an existing post release
          (``1.0.1`` -> ``1.0.1.post1`` -> ``1.0.1.post2``). Raises :class:`ValueError`
          on a pre-release or dev release -- a post release only ever follows a final
          release.

        Pre-release channels follow decision D-1:
        - Starting a channel from a FINAL version first increments the core by *base*
          (``patch`` by default, like node-semver and Poetry), so ``1.0.0`` bumped
          ``rc`` becomes ``1.0.1-rc.1``; ``base="minor"`` gives ``1.1.0-rc.1`` and
          ``base="major"`` gives ``2.0.0-rc.1``.
        - Advancing inside a channel (``rc.1`` -> ``rc.2``) or switching channel
          (``beta.2`` -> ``rc.1``) never changes ``major.minor.patch``; *base* is
          ignored once the version is already a pre-release.
        - *base* must be ``patch``, ``minor`` or ``major``. ``auto`` is a config/CLI
          value that callers resolve from commit history before calling this method.

        Kinds act on the canonical SemVer pre-release label, so a dev release bumps
        like its SemVer spelling (``0.1.0.dev1`` is ``0.1.0-0.dev.1``: ``patch``
        finalizes it to ``0.1.0``). A post release bumps like the final release it
        follows (``0.1.0.post1`` bumped ``patch`` is ``0.1.1``).

        Every returned version is strictly newer than ``self`` by :meth:`sort_key`.
        A bump that would not move forward -- such as switching ``rc`` back to
        ``alpha`` on the same core -- raises :class:`ValueError` instead.
        """
        if base not in _CONCRETE_PRERELEASE_BASES:
            if base == "auto":
                raise ValueError(
                    "Pre-release base 'auto' must be resolved from commit history "
                    "(breaking -> major, feat -> minor, otherwise patch) before calling "
                    "Version.bump(); pass 'patch', 'minor' or 'major'."
                )
            allowed = ", ".join(repr(b) for b in _CONCRETE_PRERELEASE_BASES)
            raise ValueError(f"Invalid pre-release base {base!r}; expected one of {allowed}.")
        result = self._bump_kind(kind, base)
        if not result > self:
            raise ValueError(
                f"Bump {kind!r} from {self} would produce {result}, which is not newer; "
                "a pre-release can only move forward (e.g. rc cannot switch back to "
                "alpha or beta on the same core, and a label that sorts after the "
                "channel name, such as dev.1, cannot switch to it). Bump 'major', "
                "'minor' or 'patch' first, or 'release' to finalize."
            )
        return result

    def _bump_kind(self, kind: str, base: str) -> Version:
        """Compute the bump for *kind* without the strictly-newer guard.

        The kinds act on the SemVer pre-release label (:meth:`_semver_label`), so a
        dev release behaves exactly as its canonical SemVer spelling always did
        (``0.1.0.dev1`` is ``0.1.0-0.dev.1``). A post release has no pre-release
        label and bumps like the final release it follows.
        """
        label = self._semver_label()
        match kind:
            case "major":
                if self.minor != 0 or self.patch != 0 or label is None:
                    return Version(self.major + 1, 0, 0)
                return Version(self.major, 0, 0)
            case "minor":
                if self.patch != 0 or label is None:
                    return Version(self.major, self.minor + 1, 0)
                return Version(self.major, self.minor, 0)
            case "patch":
                if label is None:
                    return Version(self.major, self.minor, self.patch + 1)
                return Version(self.major, self.minor, self.patch)
            case "release":
                return self._finalize_release(label)
            case "pre-release":
                return self._bump_pre_release(label)
            case "dev":
                return self._bump_dev(base)
            case "post":
                return self._bump_post()
            case _ if kind in PRE_RELEASE_CHANNELS:
                return self._set_channel(kind, base, label)
            case _:
                raise ValueError(f"Unknown bump kind: {kind!r}")

    def _bump_pre_release(self, label: str | None) -> Version:
        """Increment the numeric suffix of the current pre-release *label*.

        A dev release of a channel (``pre`` and ``dev`` both set) is the one
        exception: it drops ``dev`` instead of incrementing it, landing on the
        channel release itself (``1.0.1rc1.dev2`` -> ``1.0.1rc1``) rather than
        advancing further -- a dev release only ever precedes the release it is
        a dev release *of*, so "finishing" it means arriving at that release.
        """
        if label is None:
            raise ValueError(
                "Cannot bump pre-release on a stable version. "
                "Use 'alpha', 'beta', or 'rc' to start a pre-release channel."
            )
        if self.pre is not None and self.dev is not None:
            return Version(self.major, self.minor, self.patch, pre=self.pre)
        parts = label.rsplit(".", 1)
        if len(parts) == 2 and parts[1].isdigit():
            new_pre = f"{parts[0]}.{int(parts[1]) + 1}"
        else:
            new_pre = f"{label}.1"
        return Version(self.major, self.minor, self.patch, pre=new_pre)

    def _set_channel(self, channel: str, base: str, label: str | None) -> Version:
        """Start or advance a named pre-release channel (decision D-1)."""
        if label is None:
            # Stable -> pre-release: target the next *base* core, start at channel.1
            core = self._bump_kind(base, base)
            return Version(core.major, core.minor, core.patch, pre=f"{channel}.1")
        # Already on a pre-release: keep the same base version, advance the channel
        existing_channel = label.split(".")[0].lower()
        if existing_channel == channel:
            return self._bump_pre_release(label)
        # Switch to a new channel (e.g. alpha → beta); reset the counter
        return Version(self.major, self.minor, self.patch, pre=f"{channel}.1")

    def _bump_dev(self, base: str) -> Version:
        """Start or advance a dev release (RRT-VER-1 T1.3, see :meth:`bump`)."""
        if self.dev is not None:
            # Already a dev release (of a final core, or of a channel via ``pre``):
            # advance the dev number, keeping whatever it is a dev release of.
            return Version(self.major, self.minor, self.patch, pre=self.pre, dev=self.dev + 1)
        if self.pre is not None:
            if self.pre_channel is None:
                raise ValueError(
                    f"Cannot start a dev release from the opaque pre-release label "
                    f"{self.pre!r} of {self}; only alpha.N, beta.N and rc.N (N >= 1) "
                    "support a dev release."
                )
            next_pre = f"{self.pre_channel}.{(self.pre_number or 0) + 1}"
            return Version(self.major, self.minor, self.patch, pre=next_pre, dev=0)
        if self.post is not None:
            return Version(self.major, self.minor, self.patch + 1, dev=0)
        core = self._bump_kind(base, base)
        return Version(core.major, core.minor, core.patch, dev=0)

    def _bump_post(self) -> Version:
        """Start or advance a post release (RRT-VER-1 T1.3, see :meth:`bump`)."""
        if self.pre is not None or self.dev is not None:
            raise ValueError(
                f"Cannot start a post release from {self}: a post release only "
                "follows a final release (or advances an existing post release); "
                "it never follows a pre-release or dev release."
            )
        if self.post is not None:
            return Version(self.major, self.minor, self.patch, post=self.post + 1)
        return Version(self.major, self.minor, self.patch, post=1)

    def stable(self) -> Version:
        """Return the final release for this version (drop pre, build, post and dev)."""
        return Version(self.major, self.minor, self.patch)

    def _finalize_release(self, label: str | None) -> Version:
        """Finalize the current pre-release to its stable target version."""
        if label is None:
            raise ValueError(
                "Cannot finalize a version that has no pre-release. "
                "Use 'major', 'minor', or 'patch' to start a new release cycle."
            )
        return self.stable()

    def is_pre_release(self) -> bool:
        """Return True for a pre-release or a dev release (RRT-VER-1 I3).

        Final and post releases are not pre-releases; ``0.1.0.post1.dev2`` is, since
        it is a dev release.
        """
        return self.pre is not None or self.dev is not None

    def is_dev_release(self) -> bool:
        """Return True when this version carries a dev release number."""
        return self.dev is not None

    def is_post_release(self) -> bool:
        """Return True for a post release that is not itself a dev release."""
        return self.post is not None and self.dev is None

    def _semver_label(self) -> str | None:
        """Return the canonical SemVer pre-release label, or None when there is none.

        ``dev`` alone encodes as ``0.dev.M`` and ``<ch>.N`` plus ``dev`` as
        ``<ch>.(N-1).dev.M``; any other ``pre`` is returned verbatim. A post release
        (SemVer cannot express it) and a final release return None.
        """
        if self.post is not None:
            return None
        if self.dev is None:
            return self.pre
        if self.pre is None:
            return f"0.dev.{self.dev}"
        # __post_init__ guarantees a canonical <channel>.<N> label next to dev.
        channel, number = self.pre.rsplit(".", 1)
        return f"{channel}.{int(number) - 1}.dev.{self.dev}"

    def sort_key(self) -> SortKey:
        """Return the canonical precedence key for this version.

        The first five elements are the SemVer 2.0 section 11 key of the canonical
        SemVer spelling: ``major``, ``minor`` and ``patch`` numerically, then a
        stable flag (0 for a pre-release or dev release, 1 otherwise), then the
        pre-release identifiers. A dev release uses the identifiers of ``0.dev.M``
        and a channel dev release those of ``<ch>.(N-1).dev.M``.

        Pre-release labels are split on ``.`` and compared identifier by identifier,
        left to right. Numeric identifiers compare numerically and sort before
        alphanumeric ones, which compare in ASCII order. When all preceding identifiers
        are equal, the shorter list sorts first. So ``rc.2`` < ``rc.10`` and
        ``alpha`` < ``alpha.1`` < ``alpha.beta`` < ``beta``.

        The sixth element orders post releases per PEP 440: ``(0, 1, 0)`` without a
        post release, ``(N, 1, 0)`` for ``.postN`` and ``(N, 0, M)`` for
        ``.postN.devM``. So ``1.0.0`` < ``1.0.0.post1.dev0`` < ``1.0.0.post1``.

        Build metadata never takes part in precedence.
        """
        label = self._semver_label()
        if self.post is None:
            post_key = NO_POST_KEY
        else:
            post_key = (self.post, 0 if self.dev is not None else 1, self.dev or 0)
        return (
            self.major,
            self.minor,
            self.patch,
            0 if label else 1,
            _pre_release_key(label),
            post_key,
        )

    def __lt__(self, other: object) -> bool:
        """Return True when *self* has lower precedence (:meth:`sort_key`) than *other*."""
        if not isinstance(other, Version):
            return NotImplemented
        return self.sort_key() < other.sort_key()

    def __le__(self, other: object) -> bool:
        """Return True when *self* has lower or equal precedence than *other*."""
        if not isinstance(other, Version):
            return NotImplemented
        return self.sort_key() <= other.sort_key()

    def __gt__(self, other: object) -> bool:
        """Return True when *self* has higher precedence (:meth:`sort_key`) than *other*."""
        if not isinstance(other, Version):
            return NotImplemented
        return self.sort_key() > other.sort_key()

    def __ge__(self, other: object) -> bool:
        """Return True when *self* has higher or equal precedence than *other*."""
        if not isinstance(other, Version):
            return NotImplemented
        return self.sort_key() >= other.sort_key()

    def to_pep440(self) -> str:
        """Return the PEP 440 spelling (``0.1.0.dev1``, ``0.1.0a1.dev2``, ``0.1.0.post1``).

        Raises :class:`ValueError` for an opaque pre-release label PEP 440 cannot
        express (``dev.1``, ``alpha``) and for a build that is not a lowercase local
        segment, since PEP 440 would change either on the way back in.
        """
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre is not None:
            m = _CHANNEL_PRE_RE.match(self.pre) or _ZERO_CHANNEL_PRE_RE.match(self.pre)
            if m is None:
                raise ValueError(
                    f"Pre-release label {self.pre!r} of {self} has no PEP 440 spelling; "
                    "PEP 440 only knows alpha.N, beta.N and rc.N."
                )
            number = self.pre.rsplit(".", 1)[1]
            text = f"{text}{_PEP440_LETTERS[m.group('channel')]}{number}"
        if self.post is not None:
            text = f"{text}.post{self.post}"
        if self.dev is not None:
            text = f"{text}.dev{self.dev}"
        if self.build is not None:
            if _PEP440_LOCAL_RE.match(self.build) is None:
                raise ValueError(
                    f"Build {self.build!r} has no PEP 440 spelling; a PEP 440 local "
                    "segment is lowercase letters and digits separated by dots."
                )
            text = f"{text}+{self.build}"
        return text

    def __str__(self) -> str:
        """Return the canonical spelling: SemVer, or PEP 440 for a post release.

        A dev release uses the canonical SemVer encoding (``0.1.0-0.dev.1``,
        ``0.1.0-alpha.0.dev.2``). SemVer cannot express a post release, so one
        renders as PEP 440 (``0.1.0.post1``) and still parses back to itself.
        """
        if self.post is not None:
            return self.to_pep440()
        base = f"{self.major}.{self.minor}.{self.patch}"
        label = self._semver_label()
        if label:
            base = f"{base}-{label}"
        if self.build:
            base = f"{base}+{self.build}"
        return base


def _pre_release_key(pre: str | None) -> tuple[PreReleaseIdentifierKey, ...]:
    """Return the per-identifier precedence key for a pre-release label.

    Numeric identifiers map to ``(0, value, "")`` and alphanumeric ones to
    ``(1, 0, text)``, so tuple comparison puts numeric before alphanumeric, compares
    numbers numerically and text in ASCII order. A stable version yields ``()``.
    """
    if not pre:
        return ()
    return tuple(
        (0, int(ident), "") if ident.isdigit() else (1, 0, ident) for ident in pre.split(".")
    )


def newer_versions(current: Version, candidates: list[Version]) -> list[Version]:
    """Return candidates strictly newer than *current*, ascending by version.

    "Newer" and the ascending order both use canonical precedence
    (:meth:`Version.sort_key`): SemVer 2.0 section 11 precedence of the SemVer
    spelling, then PEP 440 post-release order. So ``1.0.0-rc.10`` is newer than
    ``1.0.0-rc.2`` and ``1.0.0.post1`` is newer than ``1.0.0``. Build metadata is
    ignored, so a candidate differing only in build is not newer.
    """
    ck = current.sort_key()
    fresh = [v for v in candidates if v.sort_key() > ck]
    return sorted(fresh, key=Version.sort_key)
