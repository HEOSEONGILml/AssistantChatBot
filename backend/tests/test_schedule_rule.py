from datetime import datetime, timedelta, timezone

import pytest

from backend.schedule_rule import label, next_run, validate

KST = timezone(timedelta(hours=9))


def test_daily_next_day_when_time_passed():
    after = datetime(2026, 10, 21, 9, 30, tzinfo=KST)
    assert next_run({"repeat": "daily", "time": "09:00"}, after) == datetime(2026, 10, 22, 9, 0, tzinfo=KST)


def test_daily_same_day_when_time_ahead_and_strictly_after():
    after = datetime(2026, 10, 21, 8, 0, tzinfo=KST)
    rule = {"repeat": "daily", "time": "09:00"}
    assert next_run(rule, after) == datetime(2026, 10, 21, 9, 0, tzinfo=KST)
    assert next_run(rule, datetime(2026, 10, 21, 9, 0, tzinfo=KST)) == datetime(2026, 10, 22, 9, 0, tzinfo=KST)


def test_weekdays_skips_weekend():
    after = datetime(2026, 10, 23, 15, 0, tzinfo=KST)  # 금요일
    assert next_run({"repeat": "weekdays", "time": "14:00"}, after) == datetime(2026, 10, 26, 14, 0, tzinfo=KST)


def test_weekly_monday():
    after = datetime(2026, 10, 21, 9, 0, tzinfo=KST)  # 수요일
    rule = {"repeat": "weekly", "time": "10:30", "weekday": 0}
    assert next_run(rule, after) == datetime(2026, 10, 26, 10, 30, tzinfo=KST)


def test_monthly_day_31_clamps_to_month_end():
    after = datetime(2026, 11, 1, 0, 0, tzinfo=KST)
    assert next_run({"repeat": "monthly", "time": "09:00", "day": 31}, after) == datetime(2026, 11, 30, 9, 0, tzinfo=KST)


def test_monthly_rolls_over_year():
    after = datetime(2026, 12, 31, 9, 30, tzinfo=KST)
    assert next_run({"repeat": "monthly", "time": "09:00", "day": 1}, after) == datetime(2027, 1, 1, 9, 0, tzinfo=KST)


def test_label_texts():
    assert label({"repeat": "daily", "time": "09:00"}) == "매일 09:00"
    assert label({"repeat": "weekdays", "time": "14:00"}) == "평일 14:00"
    assert label({"repeat": "weekly", "time": "10:30", "weekday": 0}) == "매주 월 10:30"
    assert label({"repeat": "monthly", "time": "09:00", "day": 1}) == "매월 1일 09:00"


def test_validate_rejects_bad_time_and_missing_weekday():
    validate({"repeat": "daily", "time": "09:00"})
    for bad in (
        {"repeat": "daily", "time": "25:00"},
        {"repeat": "daily", "time": "9:0x"},
        {"repeat": "daily"},
        {"repeat": "weekly", "time": "09:00"},
        {"repeat": "weekly", "time": "09:00", "weekday": 7},
        {"repeat": "monthly", "time": "09:00", "day": 0},
        {"repeat": "yearly", "time": "09:00"},
    ):
        with pytest.raises(ValueError):
            validate(bad)
