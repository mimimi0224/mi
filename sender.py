"""
sender.py
─────────
경제 뉴스 콘텐츠를 Gmail SMTP로 이메일 발송한다.

필요한 환경변수 (.env):
  GMAIL_ADDRESS      : 발신 Gmail 주소 (수신도 같은 주소 사용 가능)
  GMAIL_APP_PASSWORD : Gmail 앱 비밀번호 (16자리, 2단계 인증 후 발급)
  GMAIL_TO           : 수신 이메일 주소 (미설정 시 발신 주소로 자신에게 발송)
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


class SendError(Exception):
    """메시지 전송 실패."""


def _build_html(title: str, description: str, link_url: str, button_title: str) -> str:
    """뉴스 카드 형태의 HTML 이메일 본문을 생성한다."""
    desc_html = description.replace("\n", "<br>")
    return f"""
<!DOCTYPE html>
<html lang="ko">
<body style="font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;
             background:#f5f5f5;margin:0;padding:20px;">
  <div style="max-width:600px;margin:0 auto;background:#fff;
              border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1)">
    <div style="background:#1a73e8;padding:20px 24px;">
      <p style="color:#fff;margin:0;font-size:12px;opacity:.85">📈 주린이 경제 한입</p>
    </div>
    <div style="padding:24px;">
      <h2 style="margin:0 0 16px;font-size:18px;color:#202124;line-height:1.4">{title}</h2>
      <p style="margin:0 0 24px;font-size:14px;color:#5f6368;line-height:1.8">{desc_html}</p>
      <a href="{link_url}"
         style="display:inline-block;background:#1a73e8;color:#fff;
                text-decoration:none;padding:10px 20px;border-radius:6px;font-size:14px">
        {button_title}
      </a>
    </div>
  </div>
</body>
</html>"""


def send_feed(
    title: str,
    description: str,
    link_url: str,
    image_url: str = "",
    button_title: str = "전체 뉴스 보기",
) -> dict:
    """뉴스 카드를 Gmail로 발송한다."""
    address = os.environ.get("GMAIL_ADDRESS", "")
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    to_raw = os.environ.get("GMAIL_TO", address)

    if not address or not app_password:
        raise SendError(
            "GMAIL_ADDRESS 또는 GMAIL_APP_PASSWORD 환경변수가 비어 있습니다."
        )

    # 쉼표로 구분된 여러 수신자 — 개인별로 따로 발송
    recipients = [r.strip() for r in to_raw.split(",") if r.strip()]
    if not recipients:
        raise SendError("GMAIL_TO 환경변수가 비어 있습니다.")

    html = _build_html(title, description, link_url, button_title)
    failed = []

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(address, app_password)
            for recipient in recipients:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"[주린이 경제 한입] {title}"
                msg["From"] = address
                msg["To"] = recipient          # 본인 주소만 표시됨
                msg.attach(MIMEText(description, "plain", "utf-8"))
                msg.attach(MIMEText(html, "html", "utf-8"))
                try:
                    server.sendmail(address, recipient, msg.as_string())
                except smtplib.SMTPException as e:
                    failed.append(f"{recipient}: {e}")
    except smtplib.SMTPException as e:
        raise SendError(f"SMTP 로그인 실패: {e}") from e

    if failed:
        raise SendError(f"일부 발송 실패: {'; '.join(failed)}")

    return {"result": "ok", "to": recipients}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    try:
        send_feed(
            title="[테스트] 주린이 경제 한입 발송 점검",
            description="이 메시지가 보이면 Gmail SMTP 연동이 정상입니다.",
            link_url="https://finance.naver.com",
            button_title="네이버 증권",
        )
        print("발송 성공 — 받은 편지함을 확인하세요.")
    except SendError as e:
        print("실패:", e)
