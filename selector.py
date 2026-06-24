"""
selector.py
───────────
수집된 경제뉴스 CSV에서 '주린이에게 중요한' 핵심 1~2건을 고른다.

main.py 계약:
    select_top_news(csv_path: str, top_n: int = 2) -> list[dict]
        각 dict 키: title, body, url, press, date

선정 전략 (AI 호출 없이 룰 기반 → 비용 0):
    1) 키워드 점수: 제목에 핵심 경제 키워드가 많을수록 가점
    2) 동일 이슈 묶기: 제목이 비슷한 기사들은 한 그룹으로 보고 대표 1건만
       (같은 사건이 여러 언론사에서 쏟아질 때 중복 발송 방지)
    3) 그룹 점수 상위 top_n 반환
"""

import re
from difflib import SequenceMatcher

import pandas as pd

# 주린이 관점에서 중요한 핵심 키워드 (가중치 동일하게 1점씩)
PRIORITY_KEYWORDS = [
    "코스피", "코스닥", "금리", "환율", "Fed", "연준", "기준금리",
    "실적", "어닝", "유가", "국채", "물가", "CPI", "인플레이션",
    "반도체", "삼성전자", "SK하이닉스", "배당", "공매도", "상장",
    "달러", "원화", "수출", "무역", "GDP", "증시", "나스닥", "다우",
]

# 제목 유사도가 이 값 이상이면 '같은 이슈'로 간주
SIMILARITY_THRESHOLD = 0.6


def _keyword_score(title: str) -> int:
    """제목에 포함된 핵심 키워드 개수를 점수로."""
    return sum(1 for kw in PRIORITY_KEYWORDS if kw in title)


def _normalize(title: str) -> str:
    """유사도 비교용: 공백·특수문자 제거하고 소문자화."""
    return re.sub(r"[^가-힣a-zA-Z0-9]", "", str(title)).lower()


def _is_similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio() >= SIMILARITY_THRESHOLD


def select_top_news(csv_path: str, top_n: int = 2) -> list:
    """핵심 뉴스 top_n건을 dict 리스트로 반환."""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    if df.empty:
        return []

    # 1) 키워드 점수 계산
    df["score"] = df["title"].apply(_keyword_score)
    # 점수 높은 순으로 정렬 (동점이면 본문 긴 기사 우선 = 정보량 ↑)
    df["body_len"] = df["body"].astype(str).str.len()
    df = df.sort_values(["score", "body_len"], ascending=False).reset_index(drop=True)

    # 점수가 0인 기사만 있으면(키워드 미스) 그래도 본문 긴 순으로 진행
    # 2) 동일 이슈 그룹핑 — 위에서부터 보며, 이미 뽑힌 기사와 유사하면 건너뜀
    selected = []
    for _, row in df.iterrows():
        title = str(row["title"])
        if any(_is_similar(title, str(s["title"])) for s in selected):
            continue
        selected.append({
            "title": title,
            "body": str(row["body"]),
            "url": str(row.get("url", "")),
            "press": str(row.get("press", "")),
            "date": str(row.get("date", "")),
        })
        if len(selected) >= top_n:
            break

    return selected


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/raw/sample.csv"
    for i, item in enumerate(select_top_news(path), 1):
        print(f"[{i}] {item['title']}  ({item['press']})")
