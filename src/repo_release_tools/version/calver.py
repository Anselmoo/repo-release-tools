"""Calendar versioning helpers.

Supports three CalVer schemes:

* ``YYYY.MM``     — year + zero-padded month (e.g. ``2026.05``)
* ``YYYY.MM.DD``  — year + zero-padded month + day (e.g. ``2026.05.15``)
* ``YYYY.M.D``    — year + unpadded month + day (e.g. ``2026.5.15``)

Use :func:`CalVersion.today` to create a version from the current UTC date.
Use :func:`CalVersion.parse` to round-trip a version string back to a
:class:`CalVersion`.  :func:`CalVersion.bump` always returns the current
date — if today's version already exists, an optional micro counter is
incremented.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

# Matches YYYY.MM[.DD][.micro]  — padded and unpadded variants
_CALVER_RE = re.compile(
    r"^(?P<year>\d{4})\.(?P<month>\d{1,2})(?:\.(?P<day>\d{1,2})(?:\.(?P<micro>\d+))?)?$"
)

CALVER_SCHEMES = ("YYYY.MM", "YYYY.MM.DD", "YYYY.M.D")


@dataclass(frozen=True)
class CalVersion:
    """A calendar version value."""

    year: int
    month: int
    day: int | None = None
    micro: int | None = None
    scheme: str = "YYYY.MM.DD"

    @classmethod
    def today(cls, scheme: str = "YYYY.MM.DD") -> CalVersion:
        """Create a CalVersion from the current UTC date."""
        if scheme not in CALVER_SCHEMES:
            raise ValueError(
                f"Unknown CalVer scheme {scheme!r}. Choose one of: {', '.join(CALVER_SCHEMES)}"
            )
        now = dt.datetime.now(dt.UTC).date()
        if scheme == "YYYY.MM":
            return cls(now.year, now.month, scheme=scheme)
        return cls(now.year, now.month, now.day, scheme=scheme)

    @classmethod
    def parse(cls, raw: str) -> CalVersion:
        """Parse a calver string into a :class:`CalVersion`.

        The scheme is inferred from the number of components.
        """
        m = _CALVER_RE.match(raw.strip())
        if m is None:
            raise ValueError(f"Invalid CalVer: {raw!r}")
        year = int(m.group("year"))
        month = int(m.group("month"))
        day = int(m.group("day")) if m.group("day") is not None else None
        micro = int(m.group("micro")) if m.group("micro") is not None else None

        if day is None:
            scheme = "YYYY.MM"
        elif len(m.group("month")) == 2 and (len(m.group("day")) == 2 or day < 10):
            # Heuristic: both month and day are zero-padded → YYYY.MM.DD
            scheme = "YYYY.MM.DD"
        else:
            scheme = "YYYY.M.D"

        return cls(year=year, month=month, day=day, micro=micro, scheme=scheme)

    def bump(self) -> CalVersion:
        """Return a new :class:`CalVersion` for today.

        If today matches this version's year/month/day, increments the micro
        counter so the caller always gets a fresh version.
        """
        today = dt.datetime.now(dt.UTC).date()
        new_year, new_month = today.year, today.month
        new_day = today.day if self.scheme != "YYYY.MM" else None

        same_date = (
            new_year == self.year
            and new_month == self.month
            and (self.scheme == "YYYY.MM" or new_day == self.day)
        )
        new_micro = (self.micro or 0) + 1 if same_date else None
        return CalVersion(
            year=new_year,
            month=new_month,
            day=new_day,
            micro=new_micro,
            scheme=self.scheme,
        )

    def __str__(self) -> str:
        """Return the canonical calver string."""
        match self.scheme:
            case "YYYY.MM":
                base = f"{self.year}.{self.month:02d}"
            case "YYYY.MM.DD":
                assert self.day is not None
                base = f"{self.year}.{self.month:02d}.{self.day:02d}"
            case _:  # YYYY.M.D
                assert self.day is not None
                base = f"{self.year}.{self.month}.{self.day}"
        if self.micro is not None:
            base = f"{base}.{self.micro}"
        return base
