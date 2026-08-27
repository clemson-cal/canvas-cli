"""Tests for canvas_md.dates."""

import pytest

from canvas_md.dates import parse_datetime, extract_due_date, strip_inline_markup


class TestDateOnly:
    def test_two_digit_year_defaults_to_2pm(self):
        assert parse_datetime("9/8/26") == "2026-09-08T14:00:00"

    def test_four_digit_year(self):
        assert parse_datetime("9/8/2026") == "2026-09-08T14:00:00"

    def test_single_digit_month_and_day_are_zero_padded(self):
        assert parse_datetime("1/2/26") == "2026-01-02T14:00:00"

    def test_default_time_is_overridable(self):
        assert parse_datetime("9/8/26", default_time=(23, 59)) == "2026-09-08T23:59:00"


class TestWithTime:
    def test_24_hour(self):
        assert parse_datetime("9/8/26 14:05") == "2026-09-08T14:05:00"

    def test_12_hour_pm(self):
        assert parse_datetime("9/8/26 2:05pm") == "2026-09-08T14:05:00"

    def test_12_hour_am(self):
        assert parse_datetime("9/8/26 9:30am") == "2026-09-08T09:30:00"

    def test_hour_without_minutes(self):
        assert parse_datetime("9/8/26 2pm") == "2026-09-08T14:00:00"

    def test_noon_and_midnight(self):
        assert parse_datetime("9/8/26 12pm") == "2026-09-08T12:00:00"
        assert parse_datetime("9/8/26 12am") == "2026-09-08T00:00:00"

    def test_meridiem_punctuation_and_case(self):
        assert parse_datetime("9/8/26 2:05 P.M.") == "2026-09-08T14:05:00"


class TestEmpty:
    def test_none_passes_through(self):
        assert parse_datetime(None) is None

    def test_blank_is_none(self):
        assert parse_datetime("   ") is None


class TestRejects:
    @pytest.mark.parametrize("value", [
        "not a date",
        "2026-09-08",      # ISO input is not the authoring format
        "9/8",             # no year
        "13/1/26",         # month out of range
        "2/30/26",         # day does not exist in that month
        "9/8/26 25:00",    # hour out of range
        "9/8/26 13pm",     # 13 is meaningless with a meridiem
    ])
    def test_raises(self, value):
        with pytest.raises(ValueError):
            parse_datetime(value)

    def test_error_names_the_offending_value(self):
        with pytest.raises(ValueError, match="oops"):
            parse_datetime("oops")


class TestExtractDueDate:
    def test_plain_date(self):
        assert extract_due_date("# HW 3\n\n**Due**: 2/14/26\n") == "2026-02-14T14:00:00"

    def test_date_with_time(self):
        assert extract_due_date("**Due**: 2/14/26 11:59pm\n") == "2026-02-14T23:59:00"

    def test_no_due_line(self):
        assert extract_due_date("# HW 3\n\nnothing here\n") is None

    def test_unparseable_warns_but_does_not_raise(self):
        """'**Due**: TBD' is a legitimate thing to write while drafting."""
        with pytest.warns(UserWarning, match="unparseable due date"):
            assert extract_due_date("**Due**: TBD\n", source="hw3.md") is None

    def test_warning_names_the_file(self):
        with pytest.warns(UserWarning, match="hw3.md"):
            extract_due_date("**Due**: whenever\n", source="hw3.md")


class TestStripInlineMarkup:
    @pytest.mark.parametrize("raw,expected", [
        ("9/3/26", "9/3/26"),
        ("9/3/26<br>", "9/3/26"),
        ("9/3/26<br/>", "9/3/26"),
        ("9/3/26<br />", "9/3/26"),
        ("9/3/26 <BR>", "9/3/26"),
        ("9/3/26\\", "9/3/26"),
        ("9/3/26&nbsp;", "9/3/26"),
        ("9/3/26<br><br>", "9/3/26"),
        ("**9/3/26**", "9/3/26"),
        ("*9/3/26*", "9/3/26"),
        ("_9/3/26_", "9/3/26"),
        ("**9/3/26**<br>", "9/3/26"),
    ])
    def test_decoration_removed(self, raw, expected):
        assert strip_inline_markup(raw) == expected

    def test_mismatched_emphasis_left_alone(self):
        assert strip_inline_markup("**9/3/26*") == "**9/3/26*"


class TestDueLineWithMarkup:
    """A **Due** line often sits in a block of '**Key**: value<br>' lines.

    The line-ending tag used to be captured as part of the date, which failed
    to parse and was dropped with only a warning — so the assignment uploaded
    looking complete but with no due date at all.
    """

    @pytest.mark.parametrize("line", [
        "**Due**: 9/3/26<br>",
        "**Due**: 9/3/26<br/>",
        "**Due**: 9/3/26 <br />",
        "**Due**: **9/3/26**",
    ])
    def test_markup_does_not_defeat_the_date(self, line):
        assert extract_due_date(line + "\n") == "2026-09-03T14:00:00"

    def test_time_survives_markup(self):
        assert extract_due_date("**Due**: 9/3/26 11:59pm<br>\n") == "2026-09-03T23:59:00"

    def test_placeholder_still_warns(self):
        with pytest.warns(UserWarning, match="unparseable due date"):
            assert extract_due_date("**Due**: TBD<br>\n", source="hw3.md") is None

    def test_syllabus_style_block(self):
        md = (
            "# Homework 01\n\n"
            "**Due**: 9/3/26<br>\n"
            "**Points**: 4\n"
        )
        assert extract_due_date(md) == "2026-09-03T14:00:00"
