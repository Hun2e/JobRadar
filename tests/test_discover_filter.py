"""
discover.py 필터 테스트.

케이스는 실제 운영 중에 나온 오탐·누락 사례다(discover.py 주석 참고).
필터를 고칠 때 예전 오탐이 되살아나지 않는지 확인하는 용도다.
"""

from datetime import datetime, timedelta

import pytest

from discover import deadline_status, is_it_company, keyword_in, matches, parse_deadline

NOW = datetime(2026, 9, 30, 12, 0)
TODAY_DEADLINE = NOW.replace(hour=23, minute=59)
SOON_DAYS = 2
FAR_DAYS = 10


class TestKeywordIn:
    """영문 약어는 단어 경계를 따지고, 나머지는 부분 문자열로 찾는다."""

    @pytest.mark.parametrize("keyword, text", [
        ("IT", "Recruiting Specialist"),
        ("IT", "Digital Marketing"),
        ("data", "Database Administrator"),
        ("ML", "HTML 퍼블리셔"),
    ])
    def test_acronym_inside_word_is_ignored(self, keyword, text):
        assert not keyword_in(keyword, text)

    @pytest.mark.parametrize("keyword, text", [
        ("IT", "IT 직무 신입"),
        ("AI", "[AI] 모델 개발"),
        ("data", "Data Engineer"),
    ])
    def test_acronym_as_word_is_found(self, keyword, text):
        assert keyword_in(keyword, text)

    def test_korean_keyword_matches_substring(self):
        assert keyword_in("개발", "백엔드개발자")


class TestIsItCompany:
    """부분 문자열 비교의 오탐을 NOT_IT_COMPANIES로 막는다."""

    @pytest.mark.parametrize("company", ["KT", "네이버클라우드", "카카오뱅크", "LG CNS"])
    def test_it_company(self, company):
        assert is_it_company(company)

    @pytest.mark.parametrize("company", ["KT&G", "드림라인", "토스플레이스", "굿네이버스"])
    def test_name_contains_it_company_but_is_not(self, company):
        assert not is_it_company(company)

    def test_ignores_spaces_and_case(self):
        assert is_it_company("lg cns")


class TestMatches:
    def test_keyword_in_company_name_is_not_matched(self):
        # 회사명 '현대엔지니어링'이 '엔지니어'에 걸리던 오탐
        ok, _ = matches("2026 하반기 신입사원 채용", "현대엔지니어링")
        assert not ok

    def test_education_program_is_excluded_case_insensitively(self):
        ok, reason = matches("SW 개발자 CAMPUS 3기", "삼성")
        assert not ok
        assert "campus" in reason

    @pytest.mark.parametrize("title", [
        "제품품질 담당자 채용",
        "백엔드 개발자 (경력 3년 이상)",
        "SW 개발 교육생 모집",
    ])
    def test_excluded_titles(self, title):
        ok, _ = matches(title, "어떤회사")
        assert not ok

    def test_listing_with_sales_is_kept(self):
        # 'sales'를 제외어로 넣었을 때 직군 나열형 개발 공고가 잘렸다
        ok, _ = matches("Engineering/Sales/Recruiting 채용", "어떤회사")
        assert ok

    def test_newcomer_hint_is_reported(self):
        ok, reason = matches("백엔드 개발자 신입 채용", "당근")
        assert ok
        assert "신입" in reason

    def test_untitled_newcomer_hiring_only_for_it_company(self):
        title = "2026년 하반기 신입사원 채용"
        assert matches(title, "KT") == (True, "IT기업 신입공채(직무 확인 필요)")
        assert matches(title, "KT&G")[0] is False
        assert matches(title, "CJ푸드빌")[0] is False


class TestDeadline:
    def test_parse_iso_with_millis(self):
        parsed = parse_deadline("2026-09-01T23:59:00.000+09:00")
        assert parsed is not None
        assert (parsed.month, parsed.day) == (9, 1)

    @pytest.mark.parametrize("raw", [None, "", "not-a-date"])
    def test_parse_invalid_returns_none(self, raw):
        assert parse_deadline(raw) is None

    def test_status_by_days_left(self):
        assert deadline_status(None, NOW) is None
        assert deadline_status(NOW - timedelta(days=1), NOW) == "마감됨"
        assert deadline_status(TODAY_DEADLINE, NOW) == "오늘 마감"
        assert deadline_status(NOW + timedelta(days=SOON_DAYS), NOW) == f"D-{SOON_DAYS}"
        assert deadline_status(NOW + timedelta(days=FAR_DAYS), NOW) == "진행중"
