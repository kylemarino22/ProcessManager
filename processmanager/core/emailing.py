from __future__ import annotations

import os
import ssl
import smtplib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

import pandas as pd
from dotenv import load_dotenv
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# Load .env from current working dir (or specify a path)
load_dotenv()


@dataclass(frozen=True)
class EmailConfig:
    email_address: str
    email_pwd: str
    email_to: str
    email_server: str = "smtp.gmail.com"
    email_port: int = 465  # 465=SSL, 587=STARTTLS


def _require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


def get_email_details() -> EmailConfig:
    """
    Reads email config from environment variables (optionally loaded from .env).
    Required:
      - EMAIL_ADDRESS
      - EMAIL_PASSWORD
      - EMAIL_TO
    Optional:
      - EMAIL_SERVER (default smtp.gmail.com)
      - EMAIL_PORT (default 465)
    """
    email_address = _require_env("EMAIL_ADDRESS")
    email_pwd = _require_env("EMAIL_PASSWORD")
    email_to = _require_env("EMAIL_TO")

    email_server = os.getenv("EMAIL_SERVER", "smtp.gmail.com")
    email_port_str = os.getenv("EMAIL_PORT", "465")

    try:
        email_port = int(email_port_str)
    except ValueError as e:
        raise RuntimeError(f"EMAIL_PORT must be an integer, got: {email_port_str}") from e

    return EmailConfig(
        email_address=email_address,
        email_pwd=email_pwd,
        email_to=email_to,
        email_server=email_server,
        email_port=email_port,
    )


class MailType(Enum):
    plain = "plain"
    html = "html"

    def __str__(self):
        return self.value


def send_mail_file(textfile: str, subject: str):
    """
    Sends an email containing the contents of a text file (as plain text).
    """
    p = Path(textfile)
    data = p.read_text(encoding="utf-8", errors="replace")
    msg = MIMEText(data, _subtype="plain", _charset="utf-8")
    msg["Subject"] = subject
    _send_msg(msg)


def send_mail_msg(body: str, subject: str, mail_type: MailType = MailType.plain):
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg.attach(MIMEText(body, str(mail_type), "utf-8"))
    _send_msg(msg)


def send_mail_dataframe(subject: str, df: pd.DataFrame, header: str = ""):
    df_html = df.to_html(index=False)
    html = f"""\
<html>
<head>{header}</head>
<body>
{df_html}
</body>
</html>
"""
    send_mail_msg(html, subject, mail_type=MailType.html)


def send_mail_pdfs(preamble: str, filelist: List[str], subject: str):
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg.preamble = preamble

    # Helpful for many email clients:
    msg.attach(MIMEText(preamble, "plain", "utf-8"))

    for file_path in filelist:
        p = Path(file_path)
        with p.open("rb") as fp:
            attach = MIMEApplication(fp.read(), _subtype="pdf")
        attach.add_header("Content-Disposition", "attachment", filename=p.name)
        msg.attach(attach)

    _send_msg(msg)


def _smtp_send(email_server: str, email_port: int, email_address: str, email_pwd: str, msg_str: str):
    """
    Handles 465 SSL vs 587 STARTTLS properly.
    """
    if email_port == 465:
        # Implicit SSL
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(email_server, email_port, context=context) as s:
            s.login(email_address, email_pwd)
            s.sendmail(email_address, [email_address], msg_str)
    else:
        # Plain SMTP + optional STARTTLS (typical: 587)
        with smtplib.SMTP(email_server, email_port) as s:
            s.ehlo()
            try:
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
            except smtplib.SMTPException:
                # If server/port doesn't support it, continue without TLS (not recommended)
                pass
            s.login(email_address, email_pwd)
            s.sendmail(email_address, [email_address], msg_str)


def _send_msg(msg: MIMEMultipart | MIMEText):
    cfg = get_email_details()

    msg["From"] = cfg.email_address
    msg["To"] = cfg.email_to

    # Use cfg.email_to for recipients; sendmail envelope should match
    recipients = [cfg.email_to]

    # sendmail in helper currently uses [email_address]; fix to actual recipient list:
    if cfg.email_port == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(cfg.email_server, cfg.email_port, context=context) as s:
            s.login(cfg.email_address, cfg.email_pwd)
            s.sendmail(cfg.email_address, recipients, msg.as_string())
    else:
        with smtplib.SMTP(cfg.email_server, cfg.email_port) as s:
            s.ehlo()
            try:
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
            except smtplib.SMTPException:
                pass
            s.login(cfg.email_address, cfg.email_pwd)
            s.sendmail(cfg.email_address, recipients, msg.as_string())