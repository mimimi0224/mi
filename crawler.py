"""
crawler.py
──────────
Google News RSS 및 매일경제 RSS로 '어제' 경제 뉴스를 수집해
표준 스키마 CSV(data/raw/YYYY-MM-DD.csv)로 저장한다.

main.py 계약:
    crawl_yesterday() -> str   # 저장된 CSV 경로 반환
"""

import re
from datetime import date, timedelta, timezone, datetime
from pathlib import Path

import feedparser
import pandas as pd

DATA_RAW = Path("data/raw")

# (이름, URL)  — Google News는 검색어별로 여러 피드를 구성
RSS_FEEDS = [
    ("Google뉴스_경제",
     "https://news.google.com/rss/search?q=%EA%B2%BD%EC%A0%9C+%EA%B8%88%EB%A6%AC+%ED%99%98%EC%9C%A8+%EC%A6%9D%EC%8B%9C&hl=ko&gl=KR&ceid=KR:ko"),
    ("Google뉴스_코스피",
     "https://news.google.com/rss/search?q=%EC%BD%94%EC%8A%A4%ED%94%BC+%EC%BD%94%EC%8A%A4%EB%8B%A5+%EC%A3%BC%EC%8B%9D&hl=ko&gl=KR&ceid=KR:ko"),
    ("매일경제",
     "https://www.mk.co.kr/rss/40300001/"),
]

KST = timezone(timedelta(hours=9))


def _yesterday_str() -> str:
    return (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")


def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _parse_date(entry) -> str | None:
    """feedparser 시간 구조체(UTC)를 KST 날짜 문자열로 변환."""
    t = (getattr(entry, "published_parsed", None)
         or getattr(entry, "updated_parsed", None))
    if t is None:
        return None
    utc_dt = datetime(*t[:6], tzinfo=timezone.utc)
    return utc_dt.astimezone(KST).strftime("%Y-%m-%d")


def _press_name(entry, fallback: str) -> str:
    """Google News는 entry.source.title에 출처 언론사명이 있다."""
    src = getattr(entry, "source", None)
    if src:
        return getattr(src, "title", fallback)
    return fallback


def _fetch_feed(feed_name: str, url: str, target: str) -> list[dict]:
    feed = feedparser.parse(url)
    rows = []
    for entry in feed.entries:
        if _parse_date(entry) != target:
            continue

        title = _clean_html(getattr(entry, "title", ""))
        body = _clean_html(
            getattr(entry, "summary", "")
            or getattr(entry, "description", "")
            or title
        )
        link = getattr(entry, "link", "")
        press = _press_name(entry, feed_name)

        if not title:
            continue

        rows.append({
            "date": target,
            "category": "경제",
            "press": press,
            "title": title,
            "body": body,
            "url": link,
        })
    return rows


def crawl_yesterday() -> str:
    """어제 경제뉴스를 RSS 피드에서 수집해 CSV로 저장하고 경로를 반환한다."""
    target = _yesterday_str()
    DATA_RAW.mkdir(parents=True, exist_ok=True)

    rows = []
    errors = []
    for name, url in RSS_FEEDS:
        try:
            items = _fetch_feed(name, url, target)
            rows.extend(items)
        except Exception as e:
            errors.append(f"{name}: {e}")

    if not rows:
        detail = "; ".join(errors) if errors else "모든 피드에 해당 날짜 기사 없음"
        raise RuntimeError(f"{target} 경제뉴스 수집 결과가 비었습니다. ({detail})")

    df = (pd.DataFrame(rows)
          .drop_duplicates(subset=["title"])
          .reset_index(drop=True))

    out_path = DATA_RAW / f"{target}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    return str(out_path)


if __name__ == "__main__":
    try:
        p = crawl_yesterday()
        import pandas as pd
        df = pd.read_csv(p, encoding="utf-8-sig")
        print(f"수집 완료 → {p}  ({len(df)}건)")
        print(df[["press", "title"]].to_string(index=False))
    except Exception as e:
        print("수집 실패:", e)
