# 📋 자소설닷컴 공고 트래커

자소설닷컴(jasoseol.com)의 채용공고를 **자동으로 발견하고 추적**하는 시스템입니다.
관심 직무 공고를 매일 찾아내고, 등록한 공고는 매시간 마감일·경쟁률을 갱신합니다.

> 처음에는 등록한 URL만 추적하는 [Recruitment-notice-Tracking](https://github.com/Hun2e/Recruitment-notice-Tracking)으로 시작했고,
> 이 저장소에서 목록 API 기반 공고 발견 기능과 필터 회귀 테스트를 더했습니다.

---

## 두 가지 기능

| | 발견 (`discover.py`) | 추적 (`tracker.py`) |
|---|---|---|
| 하는 일 | 모르던 공고를 찾아낸다 | 아는 공고의 변화를 본다 |
| 대상 | 목록 API 전체 | `TRACK_URLS`에 등록한 URL |
| 주기 | 매일 09:00 | 매시간 |
| Notion 상태 | `발견됨` | `추적중` |
| 수집 항목 | 회사·제목·마감일·기업규모 | + 작성자 수, 직무별 작성자 수 |

**사용 흐름**: 발견기가 후보를 올려두면 → Notion에서 보고 → 관심 있는 것만
`TRACK_URLS`에 추가해 상세 추적한다.

---

## 🔄 전체 흐름

```
[매일 09:00]                        [매시간 정각]
     ↓                                   ↓
discover.py                          tracker.py
     ↓                                   ↓
목록 API 호출                     TRACK_URLS 순회 크롤링
(calendar_list.json)                     ↓
     ↓                          작성자 수·마감일 추출
제목 키워드로 필터                        ↓
     ↓                          Notion upsert ('추적중')
중복 제외 후 등록
('발견됨')
```

---

## 📁 파일 구조

```
Jasoseol-tracking/
├── .github/workflows/
│   ├── tracker.yml     ← 매시간 추적
│   ├── discover.yml    ← 매일 발견
│   └── test.yml        ← push·PR 시 필터 테스트
├── scripts/
│   ├── tracker.py      ← 상세 크롤링 + Notion 업데이트
│   └── discover.py     ← 목록 API + 키워드 필터
└── tests/
    └── test_discover_filter.py  ← 실제 오탐 사례 회귀 테스트
```

---

## 🔍 발견기가 쓰는 API

자소설닷컴 공고 목록 페이지는 JavaScript로 렌더링되어 HTML 크롤링이 되지 않습니다.
대신 페이지가 내부적으로 호출하는 API를 그대로 사용합니다.

```
POST https://jasoseol.com/employment/calendar_list.json
Body: {"start_time": "...", "end_time": "..."}
→ {"employment": [{id, name, title, end_time, business_size, ...}]}
```

한 번 호출로 두 달치 570여 건을 받습니다. robots.txt는 `/recruit`를 허용합니다.

### 필터 방식

API의 `duty_groups`는 숫자 코드만 주고 직무명을 주지 않아, **제목 키워드**로 거릅니다.

1. **제외어 먼저** — 교육과정·부트캠프·경력직·타직무를 버립니다
2. **키워드 매칭** — 제목에서 찾습니다. 회사명은 보지 않습니다
   (`현대엔지니어링`이 '엔지니어'에 걸리는 오탐 방지)
3. **영문 약어는 단어 경계 적용** — `IT`가 `Recruiting`에, `data`가
   `Database`에 걸리지 않게 합니다
4. **직무 미상 공채 구제** — "2026년 하반기 신입사원 채용"처럼 제목에 직무가
   없는 공고는 **IT 기업일 때만** 후보로 올립니다. 모든 공채를 올리면
   식품·유통·건설까지 들어와 목록이 무의미해집니다

실제 데이터 570건 기준으로 66건이 걸러집니다.

### 필터 테스트

필터를 고치다 보면 예전에 막은 오탐이 다시 들어오기 쉬워서, 운영 중 실제로 나온 사례를
`tests/test_discover_filter.py`에 테스트로 고정했습니다(30건). 회사명 키워드(`현대엔지니어링`),
약어 부분 일치(`Recruiting`, `Database`, `HTML`), 회사명 포함 오탐(`KT&G`, `드림라인`, `굿네이버스`),
대문자 교육과정(`CAMPUS`) 등이 들어 있습니다. push·PR마다 GitHub Actions에서 돌아갑니다.

```bash
python3.11 -m venv .venv && .venv/bin/pip install requests pytest
.venv/bin/python -m pytest -q tests
```

---

## 🚀 사용법

### 관심 공고를 상세 추적하기

GitHub → Settings → Secrets → `TRACK_URLS` 업데이트

```json
["https://jasoseol.com/recruit/102910", "https://jasoseol.com/recruit/123456"]
```

> ⚠️ 한 줄로 입력하고, 기존 URL도 포함해서 저장하세요.

### 키워드 바꾸기

기본값은 `discover.py`에 있습니다. 바꾸려면 Secrets에 JSON 배열로 등록합니다.

| Secret | 용도 |
|---|---|
| `KEYWORDS` | 관심 직무 키워드 |
| `EXCLUDE` | 제외 키워드 |

### 수동 실행

Actions 탭 → 워크플로 선택 → Run workflow.
발견기는 조회 기간(일)을 입력할 수 있습니다.

---

## 🔑 필요한 Secrets

| 이름 | 용도 |
|---|---|
| `NOTION_API_KEY` | Notion 통합 토큰 |
| `NOTION_DB_ID` | 대상 데이터베이스 ID |
| `TRACK_URLS` | 상세 추적할 공고 URL 배열 |
| `KEYWORDS` | (선택) 관심 키워드 |
| `EXCLUDE` | (선택) 제외 키워드 |

---

## 📊 Notion DB 속성

| 속성 | 타입 | 채우는 쪽 |
|---|---|---|
| 공고명 / 회사명 / 공고ID / 공고 URL | title, text, url | 양쪽 |
| 마감일 / 마감 상태 | date, select | 양쪽 |
| 추적 상태 | select (`발견됨`/`추적중`/`제외`) | 양쪽 |
| 기업 규모 | select | 발견기 |
| 발견일 | date | 발견기 |
| 작성자 수 / 직무별 작성자 수 | number, text | 추적기 |
