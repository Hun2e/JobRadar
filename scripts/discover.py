"""
자소설닷컴 신규 공고 발견기

기존 tracker.py가 "이미 아는 URL"을 추적한다면, 이 스크립트는
"모르던 공고를 찾아낸다". 자소설닷컴 캘린더 API에서 공고 목록을 받아
관심 키워드로 거른 뒤 Notion DB에 '발견됨' 상태로 등록한다.

사용하는 API (브라우저 개발자도구에서 확인):
    POST https://jasoseol.com/employment/calendar_list.json
    Body: {"start_time": ISO8601, "end_time": ISO8601}
    → {"employment": [ {id, name, title, end_time, business_size, ...}, ... ]}

환경변수:
    NOTION_API_KEY  필수
    NOTION_DB_ID    필수
    DISCOVER_DAYS   선택, 앞으로 며칠치를 볼지 (기본 60)
    KEYWORDS        선택, JSON 배열로 관심 키워드 덮어쓰기
    EXCLUDE         선택, JSON 배열로 제외 키워드 덮어쓰기
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests

NOTION_API_KEY = os.environ["NOTION_API_KEY"]
NOTION_DB_ID = os.environ["NOTION_DB_ID"]
DISCOVER_DAYS = int(os.environ.get("DISCOVER_DAYS", "60"))

KST = timezone(timedelta(hours=9))

LIST_API = "https://jasoseol.com/employment/calendar_list.json"
RECRUIT_URL = "https://jasoseol.com/recruit/{id}"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Referer": "https://jasoseol.com/recruit",
}

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# 관심 직무 키워드. 공고 제목에 하나라도 들어가면 후보로 본다.
# 자소설닷컴 API의 duty_groups는 숫자 코드만 주고 이름을 주지 않아
# 제목 기준으로 거른다.
DEFAULT_KEYWORDS = [
    # 개발 일반
    "개발", "엔지니어", "engineer", "developer",
    "SW", "S/W", "소프트웨어", "software",
    # 백엔드
    "백엔드", "backend", "back-end", "서버",
    "자바", "java", "스프링", "spring",
    # AI/데이터
    "AI", "인공지능", "머신러닝", "딥러닝",
    "ML", "LLM", "데이터", "data",
    "DX", "디지털",
    # QA/품질
    # '품질' 단독은 쓰지 않는다. SW QA를 노린 키워드였으나 실제로는
    # 제조 품질관리("품질 담당자", "제품품질 및 입고검사")가 훨씬 많이 걸렸다.
    # SW 쪽은 'QA'·'테스트'·'품질보증'으로 충분히 잡힌다.
    "QA", "테스트", "test", "품질보증", "SQA",
    # IT 일반 (공채에서 직무를 뭉뚱그리는 경우)
    "IT", "전산", "정보시스템", "시스템",
]

# 제외 키워드. 위 키워드에 걸려도 이게 들어가면 버린다.
#
# 실제 데이터로 시험해 보니 걸러야 할 것이 두 부류였다.
#  1) 채용이 아닌 것 - 교육과정, 부트캠프, 인재풀 등록
#  2) 직무가 다른데 회사명이나 부수 단어가 키워드에 걸린 것
#     예) "현대엔지니어링"이 '엔지니어'에, "데이터센터 구축(전기)"이 '데이터'에
DEFAULT_EXCLUDE = [
    # 채용 공고가 아닌 것
    # 첫 실행에서 교육과정이 다수 통과해 보강했다.
    # "CAMPUS"처럼 대문자로 쓰는 경우가 있어 소문자 비교에 의존한다.
    "교육생", "교육 프로그램", "교육과정", "교육 과정",
    "부트캠프", "캠퍼스", "campus", "아카데미", "academy",
    "국비", "kdt", "훈련생", "수강생", "스쿨", "school",
    "기수 모집", "전문가 과정", "양성", "연수생", "교육",
    "인재풀", "체험형", "서포터즈", "공모전", "해커톤",
    "[1기", "[2기", "[3기", "[4기", "[5기",
    # 직무 불일치
    "영업", "마케팅", "홍보", "디자인", "회계", "세무", "법무",
    "생산직", "기능직", "고졸", "전기", "설비", "시공", "건축", "토목",
    "간호", "약사", "의료", "상담원", "콜센터",
    # 첫 실행에서 걸러지지 않은 것들
    "사업개발", "상품 개발", "제조운영", "법률사무소",
    "위험률", "프로젝트 매니지먼트",
    # 2026-09-30 하반기 공고에서 걸러지지 않은 것들.
    # 제조 품질관리가 SW QA 키워드에 걸려 들어왔다.
    "제품품질", "품질관리", "입고검사", "수입검사",
    # 하드웨어 연구개발. '개발'에 걸린다(예: "매트리스 연구 개발").
    "연구 개발", "연구개발직",
    # 직무 불일치. 'associate'는 영업직 표기로만 쓰였다.
    # 'sales'는 넣지 않는다 -- "Engineering/Sales/Recruiting"처럼
    # 직군을 나열한 개발 공고까지 잘려 나갔다(실측).
    "대외협력", "associate", "재무", "구매", "물류센터",
    # 채용 형태
    "계약직", "인턴십 모집", "공개채용",
    # 경력직
    "경력", "시니어", "senior", "리드", "lead", "매니저", "팀장",
    "박사", "석사우대", "5년", "3년 이상",
]

# 신입 공채로 보이는 신호.
NEWCOMER_HINTS = ["신입", "신입사원", "공채", "대졸", "정기채용", "신입 채용"]

# IT·기술 중심 기업. 제목이 "2026년 하반기 신입사원 채용"처럼
# 직무를 밝히지 않아도, 이런 회사면 개발 직무가 있을 가능성이 높아
# 후보로 올린다. 반대로 식품·유통·건설 공채는 제외된다.
#
# 부분 문자열로 비교하므로 그룹명만 적어도 계열사가 함께 걸린다.
IT_COMPANIES = [
    # SI·IT 서비스
    "삼성SDS", "LG CNS", "SK C&C", "포스코DX", "현대오토에버",
    "CJ올리브네트웍스", "롯데이노베이트", "신세계I&C", "한화시스템",
    "아시아나IDT", "대한항공정보", "KT DS", "LG유플러스",
    # 통신·플랫폼
    "KT", "SKT", "SK텔레콤", "네이버", "카카오", "NHN", "쿠팡",
    "라인", "배달의민족", "우아한형제들", "당근", "토스", "비바리퍼블리카",
    # 전자·반도체
    "삼성전자", "SK하이닉스", "LG전자", "LG디스플레이", "삼성디스플레이",
    # 금융IT (디지털 직무 다수)
    "국민은행", "신한은행", "하나은행", "우리은행", "기업은행",
    "농협", "카카오뱅크", "케이뱅크", "삼성카드", "신한카드",
    # 보안·솔루션
    "안랩", "이스트시큐리티", "지니언스", "펜타시큐리티",
    # 기타 기술 기업
    "현대모비스", "한글과컴퓨터", "더존비즈온", "뱅크웨어글로벌",
]


# IT 기업 판정에서 제외할 회사. 부분 문자열 비교라
# "KT&G"가 "KT"에, "신한은행"과 무관한 곳이 걸리는 것을 막는다.
#
# 2026-09-30 보강: 짧은 회사명이 다른 회사 이름에 통째로 들어가는 사례를
# 실제로 확인했다. '라인'→드림라인, '토스'→토스플레이스,
# '네이버'→굿네이버스. 회사명 오탐은 EXCLUDE로는 막히지 않는다.
# 제목에 직무가 없는 공채를 IT기업이라는 이유만으로 통과시키는 경로라
# 오탐이 그대로 목록에 남는다.
NOT_IT_COMPANIES = [
    "KT&G", "KT알파", "농협하나로", "농심",
    "드림라인", "토스플레이스", "굿네이버스", "네이버스",
]


def is_it_company(company: str) -> bool:
    norm = company.replace(" ", "").lower()
    if any(x.replace(" ", "").lower() in norm for x in NOT_IT_COMPANIES):
        return False
    return any(k.replace(" ", "").lower() in norm for k in IT_COMPANIES)


def load_list(names_env, default):
    raw = os.environ.get(names_env)
    if not raw:
        return default
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and parsed:
            return [str(x) for x in parsed]
    except json.JSONDecodeError:
        print(f"[WARN] {names_env} 파싱 실패, 기본값을 씁니다.")
    return default


KEYWORDS = load_list("KEYWORDS", DEFAULT_KEYWORDS)
EXCLUDE = load_list("EXCLUDE", DEFAULT_EXCLUDE)

SIZE_LABEL = {
    "big_business": "대기업",
    "middle_market": "중견기업",
}


def fetch_employments(days: int) -> list[dict]:
    """앞으로 days일치 공고 목록을 받아온다."""
    now = datetime.now(KST)
    body = {
        # 어제부터 조회해 오늘 마감 공고도 포함시킨다
        "start_time": (now - timedelta(days=1)).astimezone(timezone.utc).isoformat(),
        "end_time": (now + timedelta(days=days)).astimezone(timezone.utc).isoformat(),
    }
    try:
        resp = requests.post(LIST_API, headers=BROWSER_HEADERS, json=body, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 목록 API 요청 실패: {e}")
        return []

    data = resp.json()
    return data.get("employment", [])


# 짧은 영문 약어는 다른 단어 속에 우연히 들어가기 쉽다.
# 예: 'IT'는 Recruiting·Specialist·Digital에, 'ML'은 HTML에 걸린다.
# 이런 키워드는 앞뒤가 알파벳이 아닐 때만 인정한다.
ACRONYMS = {"it", "ai", "ml", "sw", "qa", "dx", "llm", "data", "test"}


def keyword_in(keyword: str, text: str) -> bool:
    """키워드가 텍스트에 있는지 본다. 영문 약어는 단어 경계를 따진다."""
    k = keyword.lower()
    if k in ACRONYMS:
        return re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", text.lower()) is not None
    return k in text.lower()


def matches(title: str, company: str) -> tuple[bool, str]:
    """관심 공고인지 판정하고 사유를 함께 돌려준다.

    키워드는 '제목'에서만 찾는다. 회사명까지 넣으면 현대엔지니어링이
    '엔지니어'에, NHN Cloud가 'Cloud'에 걸리는 오탐이 생긴다.
    제외어는 제목과 회사명 양쪽에서 본다.
    """
    both_low = f"{title} {company}".lower()

    # 제외 먼저. 교육과정 등은 키워드가 뭐든 버린다.
    blocked = next((x for x in EXCLUDE if x.lower() in both_low), None)
    if blocked:
        return False, f"제외어 '{blocked}'"

    hit = next((k for k in KEYWORDS if keyword_in(k, title)), None)
    if hit:
        # 신입 공채면 더 확실한 후보다
        if any(h in title for h in NEWCOMER_HINTS):
            return True, f"'{hit}' + 신입"
        return True, f"'{hit}'"

    # 제목에 직무가 없는 신입 공채는 IT 기업일 때만 후보로 올린다.
    # "2026년 하반기 신입사원 채용"은 상세를 봐야 직무를 아는데,
    # 모든 공채를 올리면 식품·유통·건설까지 들어와 목록이 무의미해진다.
    if any(h in title for h in NEWCOMER_HINTS) and is_it_company(company):
        return True, "IT기업 신입공채(직무 확인 필요)"

    return False, "키워드 불일치"


def parse_deadline(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        # "2026-09-01T23:59:00.000+09:00" 형태
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def deadline_status(deadline: datetime | None, now: datetime) -> str | None:
    if not deadline:
        return None
    diff = (deadline.date() - now.date()).days
    if diff < 0:
        return "마감됨"
    if diff == 0:
        return "오늘 마감"
    if diff <= 3:
        return f"D-{diff}"
    return "진행중"


def existing_job_ids() -> set[str]:
    """이미 DB에 있는 공고ID를 모두 모은다 (중복 등록 방지)."""
    ids: set[str] = set()
    payload: dict = {"page_size": 100}
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"

    while True:
        try:
            r = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=20)
            r.raise_for_status()
        except Exception as e:
            print(f"[ERROR] 기존 목록 조회 실패: {e}")
            return ids

        data = r.json()
        for row in data.get("results", []):
            prop = row.get("properties", {}).get("공고ID", {})
            for chunk in prop.get("rich_text", []):
                text = chunk.get("plain_text", "").strip()
                if text:
                    ids.add(text)

        if not data.get("has_more"):
            break
        payload["start_cursor"] = data["next_cursor"]

    return ids


def create_page(job: dict, now: datetime) -> bool:
    deadline = job["deadline"]
    props = {
        "공고명": {"title": [{"text": {"content": f"[{job['company']}] {job['title']}"[:2000]}}]},
        "회사명": {"rich_text": [{"text": {"content": job["company"][:2000]}}]},
        "공고ID": {"rich_text": [{"text": {"content": job["id"]}}]},
        "공고 URL": {"url": job["url"]},
        "추적 상태": {"select": {"name": "발견됨"}},
        "발견일": {"date": {"start": now.isoformat()}},
        "최근 업데이트": {"date": {"start": now.isoformat()}},
    }

    if job["size_label"]:
        props["기업 규모"] = {"select": {"name": job["size_label"]}}

    if deadline:
        props["마감일"] = {"date": {"start": deadline.isoformat()}}
        status = deadline_status(deadline, now)
        if status:
            props["마감 상태"] = {"select": {"name": status}}

    try:
        r = requests.post(
            "https://api.notion.com/v1/pages",
            headers=NOTION_HEADERS,
            json={"parent": {"database_id": NOTION_DB_ID}, "properties": props},
            timeout=20,
        )
    except Exception as e:
        print(f"  [ERROR] 등록 실패: {e}")
        return False

    if r.status_code in (200, 201):
        return True
    print(f"  [ERROR] Notion {r.status_code}: {r.text[:200]}")
    return False


def main():
    now = datetime.now(KST)
    print(f"\n{'=' * 56}")
    print(f"신규 공고 발견: {now.strftime('%Y-%m-%d %H:%M:%S KST')}")
    print(f"조회 범위: 앞으로 {DISCOVER_DAYS}일")
    print(f"{'=' * 56}\n")

    employments = fetch_employments(DISCOVER_DAYS)
    if not employments:
        print("공고 목록을 받지 못했습니다.")
        sys.exit(1)
    print(f"전체 공고 {len(employments)}건 수신\n")

    known = existing_job_ids()
    print(f"DB에 이미 있는 공고 {len(known)}건\n")

    candidates = []
    for item in employments:
        job_id = str(item.get("id", "")).strip()
        if not job_id:
            continue

        title = (item.get("title") or "").strip()
        company = (item.get("name") or "").strip()

        ok, reason = matches(title, company)
        if not ok:
            continue

        if job_id in known:
            print(f"  (이미 있음) [{company}] {title}")
            continue

        candidates.append({
            "id": job_id,
            "url": RECRUIT_URL.format(id=job_id),
            "company": company,
            "title": title,
            "deadline": parse_deadline(item.get("end_time")),
            "size_label": SIZE_LABEL.get(item.get("business_size")),
            "reason": reason,
        })

    print(f"\n신규 후보 {len(candidates)}건\n")

    added = 0
    for job in candidates:
        label = f"[{job['company']}] {job['title']}"
        if create_page(job, now):
            added += 1
            deadline_txt = (
                job["deadline"].strftime("%Y-%m-%d") if job["deadline"] else "마감일 미상"
            )
            print(f"  + {label}")
            print(f"    {deadline_txt} · 매칭 {job['reason']}")

    print(f"\n{'=' * 56}")
    print(f"신규 등록 {added}건 / 후보 {len(candidates)}건")
    print("Notion에서 '발견됨' 상태를 확인하고, 추적할 공고는")
    print("'추적중'으로 바꾼 뒤 TRACK_URLS에 추가하세요.")
    print(f"{'=' * 56}\n")


if __name__ == "__main__":
    main()
