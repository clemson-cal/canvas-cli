"""Date/time parsing shared by the CLI, plugins, and markdown metadata lines.

Canvas wants ISO8601. Course authors want to type ``9/8/26``. This module is
the single place that bridges the two, so the accepted syntax stays identical
whether a date arrives from a ``**Due**:`` line, a ``--due`` flag, or a
plugin's own option.
"""

import re
import warnings
from datetime import datetime
from typing import Optional

#: Time of day used when a date is given without one.
DEFAULT_TIME = (14, 0)

#: Human-readable syntax summary, for argparse help strings.
SYNTAX_HELP = "M/D/YY, optionally with a time: '9/8/26', '9/8/26 14:05', '9/8/26 2:05pm'"

_DATETIME_RE = re.compile(
    r"""^\s*
    (?P<month>\d{1,2}) / (?P<day>\d{1,2}) / (?P<year>\d{2,4})
    (?:\s+
        (?P<hour>\d{1,2})
        (?: : (?P<minute>\d{2}) )?
        \s* (?P<meridiem>[ap]\.?m\.?)?
    )?
    \s*$""",
    re.VERBOSE | re.IGNORECASE,
)


def parse_datetime(value: Optional[str], default_time=DEFAULT_TIME) -> Optional[str]:
    """Parse a course-author date into a Canvas-ready ISO8601 string.

    Accepts ``M/D/YY`` and ``M/D/YYYY``, optionally followed by a time in
    either 24-hour (``14:05``) or 12-hour (``2:05pm``, ``2pm``) form. Without
    a time, ``default_time`` is used — 2:00 PM, matching when this course's
    assignments have historically been due.

    The returned timestamp carries no UTC offset; Canvas interprets it in the
    course's configured timezone.

    Args:
        value: The string to parse, or None.
        default_time: ``(hour, minute)`` applied when no time is given.

    Returns:
        ``YYYY-MM-DDTHH:MM:SS``, or None if ``value`` is None or empty.

    Raises:
        ValueError: If the string is not a recognized date, or names a day
            that does not exist. Callers should let this surface — a silently
            ignored date is far worse than a loud one, particularly for a quiz
            window that is supposed to close during class.
    """
    if value is None:
        return None
    if not value.strip():
        return None

    match = _DATETIME_RE.match(value)
    if not match:
        raise ValueError(f"Could not parse date {value!r}. Expected {SYNTAX_HELP}.")

    parts = match.groupdict()

    year = int(parts["year"])
    if year < 100:
        year += 2000

    if parts["hour"] is None:
        hour, minute = default_time
    else:
        hour = int(parts["hour"])
        minute = int(parts["minute"] or 0)
        meridiem = (parts["meridiem"] or "").replace(".", "").lower()
        if meridiem:
            if not 1 <= hour <= 12:
                raise ValueError(f"Hour {hour} is not valid with '{meridiem}' in {value!r}.")
            hour = hour % 12 + (12 if meridiem == "pm" else 0)

    try:
        parsed = datetime(year, int(parts["month"]), int(parts["day"]), hour, minute)
    except ValueError as exc:
        raise ValueError(f"Could not parse date {value!r}: {exc}.") from exc

    return parsed.strftime("%Y-%m-%dT%H:%M:%S")


_DUE_LINE_RE = re.compile(r"\*\*Due\*\*:\s*(.+?)\s*$", re.MULTILINE)


def extract_due_date(md_content: str, source: str = "markdown") -> Optional[str]:
    """Pull a ``**Due**: ...`` line out of markdown, leniently.

    Deliberately more forgiving than :func:`parse_datetime`: a hand-edited
    assignment may say ``**Due**: TBD``, and that should warn rather than
    abort an upload. Command-line flags take the strict path instead, where a
    typo means a deadline silently never applies.

    Args:
        md_content: Full markdown text.
        source: Name used in the warning message.

    Returns:
        ISO8601 string, or None if there is no due line or it is unparseable.
    """
    match = _DUE_LINE_RE.search(md_content)
    if not match:
        return None
    try:
        return parse_datetime(match.group(1))
    except ValueError as exc:
        warnings.warn(f"{source}: ignoring unparseable due date — {exc}")
        return None
