from datetime import date

from app.services.date_parser import DateParser


def _p(txt, base=date(2026,5,5)):
    return DateParser().parse(txt, base_date=base)


def test_parse_today(): assert _p("今天").date == "2026-05-05"
def test_parse_tomorrow(): assert _p("明天").date == "2026-05-06"
def test_parse_day_after_tomorrow(): assert _p("后天").date == "2026-05-07"
def test_parse_three_days_later(): assert _p("大后天").date == "2026-05-08"
def test_parse_chinese_month_day_hao(): assert _p("5月10号").date == "2026-05-10"
def test_parse_chinese_month_day_ri(): assert _p("5月10日").date == "2026-05-10"
def test_parse_chinese_number_month_day(): assert _p("五月十号").date == "2026-05-10"
def test_parse_chinese_number_december(): assert _p("十二月三十一号").date == "2026-12-31"
def test_parse_iso_date(): assert _p("2026-05-10").date == "2026-05-10"
def test_parse_slash_month_day(): assert _p("5/10").date == "2026-05-10"
def test_parse_dash_month_day(): assert _p("5-10").date == "2026-05-10"
def test_parse_dot_full_date(): assert _p("2026.05.10").date == "2026-05-10"
def test_parse_next_monday(): assert _p("下周一").date == "2026-05-11"
def test_parse_friday_future_nearest(): assert _p("周五").date == "2026-05-08"
def test_parse_this_week_monday(): assert _p("本周一").date == "2026-05-04"
def test_parse_next_year_inferred(): assert _p("1月2号", date(2026,12,30)).date == "2027-01-02"
def test_parse_unknown_date(): assert _p("五月十几号").status == "unparsed"
def test_parse_past_date_warning(): assert "parsed_date_is_in_past" in (_p("4月30号").message or "")
