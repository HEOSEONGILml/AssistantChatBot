"""스케줄 규칙: 규칙 dict에서 다음 실행 시각과 표시 글을 구한다."""

import calendar
import re
from datetime import datetime, timedelta

_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
_REPEATS = ("daily", "weekdays", "weekly", "monthly")


def validate(rule: dict) -> None:
    repeat = rule.get("repeat")
    if repeat not in _REPEATS:
        raise ValueError(f"알 수 없는 반복: {repeat!r}")
    _parse_time(rule.get("time"))
    if repeat == "weekly":
        weekday = rule.get("weekday")
        if not isinstance(weekday, int) or isinstance(weekday, bool) or not 0 <= weekday <= 6:
            raise ValueError("weekly에는 0~6 weekday가 필요하다")
    if repeat == "monthly":
        day = rule.get("day")
        if not isinstance(day, int) or isinstance(day, bool) or not 1 <= day <= 31:
            raise ValueError("monthly에는 1~31 day가 필요하다")


def _parse_time(value) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{2}):(\d{2})", value) if isinstance(value, str) else None
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        raise ValueError(f"시각은 HH:MM이어야 한다: {value!r}")
    return int(m[1]), int(m[2])


def label(rule: dict) -> str:
    time = rule["time"]
    match rule["repeat"]:
        case "daily":
            return f"매일 {time}"
        case "weekdays":
            return f"평일 {time}"
        case "weekly":
            return f"매주 {_WEEKDAYS[rule['weekday']]} {time}"
        case "monthly":
            return f"매월 {rule['day']}일 {time}"
    raise ValueError(f"알 수 없는 반복: {rule['repeat']!r}")


def _matches_day(rule: dict, d: datetime) -> bool:
    match rule["repeat"]:
        case "daily":
            return True
        case "weekdays":
            return d.weekday() < 5
        case "weekly":
            return d.weekday() == rule["weekday"]
        case "monthly":
            # 31일 규칙은 짧은 달의 마지막 날에 돈다
            return d.day == min(rule["day"], calendar.monthrange(d.year, d.month)[1])
    raise ValueError(f"알 수 없는 반복: {rule['repeat']!r}")


def next_run(rule: dict, after: datetime) -> datetime:
    """after보다 엄격히 뒤인 첫 실행 시각. after의 tz를 유지한다."""
    validate(rule)
    hour, minute = _parse_time(rule["time"])
    day = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # 월간 규칙의 최대 간격은 약 한 달이라 62일이면 충분하다
    for _ in range(62):
        if day > after and _matches_day(rule, day):
            return day
        day = (day.replace(tzinfo=None) + timedelta(days=1)).replace(tzinfo=after.tzinfo)
    raise ValueError("다음 실행 시각을 찾지 못했다")
