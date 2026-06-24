"""
main.py
───────
주린이 경제 뉴스 → 카카오톡 발송 파이프라인의 진입점.

흐름:
  crawler.crawl_yesterday()        # 어제 경제뉴스 수집 → CSV 경로
      ↓
  selector.select_top_news(csv, n) # 핵심 1~2건 선정 → list[dict]
      ↓
  writer.rewrite_for_beginners(it) # 주린이용 풀어쓰기 → dict
      ↓
  sender.send_feed(...)            # 카카오톡 '나에게 보내기'

매일 09:00 cron / GitHub Actions 가 이 파일을 실행한다:
    python main.py
점검만 하고 실제 발송은 막고 싶으면:
    python main.py --dry-run

───────────────────────────────────────────────────────────
[ 상위 모듈이 지켜야 할 인터페이스 계약 ]

crawler.crawl_yesterday() -> str
    어제 날짜 경제뉴스를 수집해 CSV로 저장하고, 그 파일 경로를 반환.

selector.select_top_news(csv_path: str, top_n: int = 2) -> list[dict]
    각 dict 키: title, body, url, press, date

writer.rewrite_for_beginners(news_item: dict) -> dict
    반환 키:
      headline         : str  (한 줄 헤드라인)
      what_happened    : str
      why_matters      : str
      terms            : list[{"term": str, "easy_explain": str}]
      one_line_summary : str
───────────────────────────────────────────────────────────
"""

import argparse
import logging
import sys
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import crawler
import selector
import writer
import sender

# ── 로깅 설정 ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("juriny")

# 한 번에 다룰 뉴스 개수 (1~2개 권장)
TOP_N = 2

DESC_MAX = 10000


def build_feed_payload(rewritten: dict, source_url: str) -> dict:
    """
    writer 결과(dict)를 카카오 피드 메시지용 인자로 변환한다.
    제목 = 헤드라인 / 설명 = 무슨일·왜중요·용어·한줄요약을 압축.
    """
    terms_line = " · ".join(
        f"{t['term']}: {t['easy_explain']}" for t in rewritten.get("terms", [])
    )

    parts = [
        rewritten.get("what_happened", "").strip(),
        f"💡 왜 중요? {rewritten.get('why_matters', '').strip()}",
    ]
    if terms_line:
        parts.append(f"📚 용어 — {terms_line}")
    parts.append(f"✅ 한 줄 요약: {rewritten.get('one_line_summary', '').strip()}")

    description = "\n\n".join(p for p in parts if p)
    if len(description) > DESC_MAX:
        description = description[: DESC_MAX - 1] + "…"

    return {
        "title": rewritten.get("headline", "오늘의 경제 한입"),
        "description": description,
        "link_url": source_url,
        "button_title": "전체 뉴스 보기",
    }


def run(dry_run: bool = False) -> int:
    """
    파이프라인 1회 실행. 성공 시 0, 실패 시 1 반환(스케줄러 종료코드용).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    log.info("=== 주린이 경제 한입 파이프라인 시작 (%s) ===", today)

    # [1] 수집 ────────────────────────────────────────────
    try:
        csv_path = crawler.crawl_yesterday()
        log.info("[1/4] 수집 완료 → %s", csv_path)
    except Exception as e:
        log.error("[1/4] 수집 실패: %s", e)
        return 1

    # [2] 선정 ────────────────────────────────────────────
    try:
        items = selector.select_top_news(csv_path, top_n=TOP_N)
        if not items:
            log.warning("[2/4] 선정된 뉴스가 0건 → 오늘은 발송 생략")
            return 0
        log.info("[2/4] 선정 완료 → %d건", len(items))
    except Exception as e:
        log.error("[2/4] 선정 실패: %s", e)
        return 1

    # [3]+[4] 풀어쓰기 → 발송 (뉴스 건별로 처리) ─────────────
    sent, failed = 0, 0
    for idx, item in enumerate(items, start=1):
        title = item.get("title", "(제목없음)")
        try:
            rewritten = writer.rewrite_for_beginners(item)
            log.info("[3/4] (%d) 풀어쓰기 완료 — %s", idx, rewritten.get("headline", title))
        except Exception as e:
            log.error("[3/4] (%d) 풀어쓰기 실패 (%s): %s", idx, title, e)
            failed += 1
            continue

        payload = build_feed_payload(rewritten, item.get("url", ""))

        if dry_run:
            log.info("[4/4] (%d) [DRY-RUN] 발송 생략. 미리보기:\n%s\n%s",
                     idx, payload["title"], payload["description"])
            sent += 1
            continue

        try:
            sender.send_feed(**payload)
            log.info("[4/4] (%d) 카카오톡 발송 성공", idx)
            sent += 1
        except Exception as e:
            log.error("[4/4] (%d) 발송 실패: %s", idx, e)
            failed += 1

    log.info("=== 종료: 성공 %d건 / 실패 %d건 ===", sent, failed)
    # 한 건이라도 실패하면 비정상 종료코드 → 스케줄러 로그/알림에서 감지 가능
    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="주린이 경제 뉴스 카카오톡 발송")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 발송 없이 생성 결과만 출력해 점검",
    )
    args = parser.parse_args()
    sys.exit(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
