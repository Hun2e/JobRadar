"""
테스트 공통 설정.

discover.py는 import 시점에 NOTION_API_KEY·NOTION_DB_ID를 읽고,
KEYWORDS·EXCLUDE 환경변수가 있으면 기본 목록을 덮어쓴다.
필터 테스트는 기본 목록을 기준으로 하므로 가짜 키만 넣고 덮어쓰기 변수는 지운다.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("NOTION_API_KEY", "test-key")
os.environ.setdefault("NOTION_DB_ID", "test-db")
os.environ.pop("KEYWORDS", None)
os.environ.pop("EXCLUDE", None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
