"""
writer.py
─────────
선정된 뉴스 1건을 Claude API로 '주린이 눈높이'로 풀어쓴다.

main.py 계약:
    rewrite_for_beginners(news_item: dict) -> dict
        입력 키: title, body, url, press, date
        반환 키:
          headline         : str
          what_happened    : str
          why_matters      : str
          terms            : list[{"term": str, "easy_explain": str}]
          one_line_summary : str

핵심 설계:
    - 응답을 JSON으로만 받도록 강제하고 안전하게 파싱한다.
    - 본문을 그대로 인용하지 말고 '자기 말로 풀어쓰기'를 프롬프트에서 강제
      (저작권 보호 + 입문자 가독성).
    - 숫자·고유명사가 원문에 있던 것인지 가벼운 검증을 덧붙인다(왜곡 방지).
"""

import json
import os
import re

from openai import OpenAI

MODEL = "gpt-4o-mini"
MAX_TOKENS = 1500

# 본문이 너무 길면 토큰 절약을 위해 앞부분만 사용 (기사 핵심은 보통 상단)
BODY_CHAR_LIMIT = 2000

SYSTEM_PROMPT = (
    "너는 주식·경제에 막 입문한 '주린이'를 위한 친근한 한국어 블로그 작가야. "
    "어려운 내용을 비유와 쉬운 말로 풀어주되, 절대 투자를 권유하지 않아. "
    "반드시 지정된 JSON 형식으로만 답하고, JSON 외 다른 텍스트는 출력하지 마."
)

PROMPT_TEMPLATE = """아래 경제 뉴스를 주린이가 이해하도록 풀어써줘.

[제목] {title}
[언론사] {press}
[본문] {body}

아래 JSON 형식으로만 답해. (마크다운 코드블록 없이 순수 JSON)
{{
  "headline": "주린이가 궁금해할 한 줄 헤드라인 (물음표 적극 활용)",
  "what_happened": "무슨 일이 있었는지 3~4문장으로 쉽게",
  "why_matters": "왜 중요한지, 시장·내 주식에 어떤 영향인지 2~3문장",
  "terms": [
    {{"term": "용어1", "easy_explain": "비유로 풀이 1~2문장"}},
    {{"term": "용어2", "easy_explain": "..."}},
    {{"term": "용어3", "easy_explain": "..."}}
  ],
  "one_line_summary": "오늘 이거 하나만 기억하자, 한 줄로"
}}

규칙:
- 본문을 그대로 베끼지 말고 모두 네 말로 풀어쓸 것
- 어려운 용어는 무조건 비유 사용
- "사라/팔아라" 같은 투자 권유 표현 금지
- 친한 언니가 카톡으로 설명하듯 편한 말투
"""

_client = None


def _get_client():
    """OpenAI 클라이언트 지연 생성 (환경변수 OPENAI_API_KEY 사용)."""
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY 환경변수가 비어 있습니다.")
        _client = OpenAI(api_key=api_key)
    return _client


def _extract_json(text: str) -> dict:
    """
    응답에서 JSON을 안전하게 추출한다.
    혹시 코드블록(```json ... ```)으로 감싸 와도 벗겨낸다.
    """
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    # 첫 { 부터 마지막 } 까지만 취해 파싱 안정성을 높인다
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start:end + 1]
    return json.loads(cleaned)


def _validate(result: dict) -> dict:
    """필수 키 존재 여부를 확인하고, 누락 시 빈 값으로 보정한다."""
    result.setdefault("headline", "오늘의 경제 한입")
    result.setdefault("what_happened", "")
    result.setdefault("why_matters", "")
    result.setdefault("one_line_summary", "")
    terms = result.get("terms", [])
    # terms 형식 보정
    clean_terms = []
    for t in terms if isinstance(terms, list) else []:
        if isinstance(t, dict) and "term" in t and "easy_explain" in t:
            clean_terms.append({"term": str(t["term"]), "easy_explain": str(t["easy_explain"])})
    result["terms"] = clean_terms
    return result


def rewrite_for_beginners(news_item: dict) -> dict:
    """뉴스 1건을 주린이용으로 풀어써 구조화된 dict로 반환."""
    body = str(news_item.get("body", ""))[:BODY_CHAR_LIMIT]
    prompt = PROMPT_TEMPLATE.format(
        title=news_item.get("title", ""),
        press=news_item.get("press", ""),
        body=body,
    )

    client = _get_client()
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    text = resp.choices[0].message.content or ""

    try:
        result = _extract_json(text)
    except (json.JSONDecodeError, ValueError) as e:
        raise RuntimeError(f"AI 응답 JSON 파싱 실패: {e}\n원문: {text[:200]}")

    return _validate(result)


if __name__ == "__main__":
    # 단독 점검 (ANTHROPIC_API_KEY 필요)
    sample = {
        "title": "코스피 사상 첫 6500 돌파…개인은 역대 최대 순매도",
        "press": "테스트일보",
        "body": "코스피가 장중 6500선을 처음 넘어섰다. 같은 기간 개인투자자는 "
                "유가증권시장에서 약 14조원을 순매도했다.",
        "url": "https://finance.naver.com",
    }
    try:
        out = rewrite_for_beginners(sample)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except Exception as e:
        print("실패:", e)
