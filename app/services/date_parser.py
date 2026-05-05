from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta


@dataclass
class DateParseResult:
    input_text: str | None
    date: str | None
    status: str
    message: str | None = None
    warnings: list[str] = field(default_factory=list)


class DateParser:
    _relative_map = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}
    _weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6, "七": 6}

    def parse(self, date_input: str | None, *, base_date: date | None = None) -> DateParseResult:
        base = base_date or date.today()
        if not date_input or not date_input.strip():
            return DateParseResult(input_text=None, date=base.isoformat(), status="defaulted", message="defaulted_to_today")

        text = date_input.strip()

        parsed = self._parse_relative(text, base) or self._parse_weekday(text, base) or self._parse_numeric(text, base) or self._parse_cn_month_day(text, base)
        if not parsed:
            return DateParseResult(input_text=text, date=None, status="unparsed", message="unparsed_date_input")

        warnings: list[str] = []
        if parsed < base:
            warnings.append("parsed_date_is_in_past")
        msg = ",".join(warnings) if warnings else None
        return DateParseResult(input_text=text, date=parsed.isoformat(), status="parsed", message=msg, warnings=warnings)

    def _parse_relative(self, text: str, base: date) -> date | None:
        if text in self._relative_map:
            return base + timedelta(days=self._relative_map[text])
        return None

    def _parse_weekday(self, text: str, base: date) -> date | None:
        m = re.fullmatch(r"(本周|这周|下周|下星期|周|星期)?([一二三四五六日天七])", text)
        if not m:
            return None
        prefix, wd = m.groups()
        target = self._weekday_map[wd]
        start = base - timedelta(days=base.weekday())
        if prefix in {"本周", "这周"}:
            return start + timedelta(days=target)
        if prefix in {"下周", "下星期"}:
            return start + timedelta(days=7 + target)
        delta = (target - base.weekday()) % 7
        return base + timedelta(days=delta)

    def _parse_numeric(self, text: str, base: date) -> date | None:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                pass
        m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})", text)
        if not m:
            return None
        month, day = int(m.group(1)), int(m.group(2))
        return self._resolve_year(month, day, base)

    def _parse_cn_month_day(self, text: str, base: date) -> date | None:
        m = re.fullmatch(r"([0-9一二三四五六七八九十十二]+)月([0-9一二三四五六七八九十]+)(?:号|日)", text)
        if not m:
            return None
        month = self._cn_to_int(m.group(1))
        day = self._cn_to_int(m.group(2))
        if month is None or day is None:
            return None
        return self._resolve_year(month, day, base)

    def _resolve_year(self, month: int, day: int, base: date) -> date | None:
        try:
            candidate = date(base.year, month, day)
        except ValueError:
            return None
        if (base - candidate).days > 30:
            try:
                return date(base.year + 1, month, day)
            except ValueError:
                return None
        return candidate

    def _cn_to_int(self, s: str) -> int | None:
        if s.isdigit():
            return int(s)
        mapping = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}
        if s == "十":
            return 10
        if s == "十一":
            return 11
        if s == "十二":
            return 12
        if s.startswith("十") and len(s) == 2:
            return 10 + mapping.get(s[1], 0)
        if s.endswith("十"):
            return mapping.get(s[0], 0) * 10
        if "十" in s:
            a,b = s.split("十",1)
            return mapping.get(a,0)*10 + mapping.get(b,0)
        return mapping.get(s)
