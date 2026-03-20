#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import List, Dict, Any

import feedparser
from dotenv import load_dotenv
from openai import OpenAI

MAX_ITEMS_PER_TOPIC = 6


def load_config() -> tuple[OpenAI, str, Path, list[dict[str, Any]]]:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY が未設定です。")

    model = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()
    output_dir = Path(os.path.expanduser(os.getenv("OUTPUT_DIR", "~/Documents/morning_reports")))
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(Path(__file__).with_name("sources.json"), "r", encoding="utf-8") as f:
        sources = json.load(f)["topics"]

    client = OpenAI(api_key=api_key)
    return client, model, output_dir, sources


def strip_html(text: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def collect_feed_items(feed_urls: List[str]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    seen = set()

    for url in feed_urls:
        feed = feedparser.parse(url)
        feed_title = feed.feed.get("title", url)

        for entry in feed.entries[:10]:
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "") or entry.get("description", "")
            published = (entry.get("published", "") or entry.get("updated", "")).strip()

            if not title or not link or link in seen:
                continue

            seen.add(link)
            items.append({
                "title": title,
                "link": link,
                "summary": strip_html(summary)[:500],
                "published": published,
                "source": feed_title,
            })

    items.sort(key=lambda x: x.get("published", ""), reverse=True)
    return items[:MAX_ITEMS_PER_TOPIC]


def build_prompt(topics: list[dict[str, Any]], today: str) -> str:
    lines = [
        f"今日は {today} です。",
        "あなたは朝レポートを作るアシスタントです。",
        "以下の情報を日本語で整理してください。",
        "",
        "【出力条件】",
        "1. 重要度順に整理する",
        "2. 事実と推測を分ける",
        "3. 中小企業、製造業現場、Webアプリ開発、個人のAI活用に落とし込む",
        "4. 抽象論ではなく具体策を優先する",
        "5. 各トピックの末尾に参照URLを1件以上残す",
        "",
        "【出力形式】",
        "# 今日の朝レポート",
        "## 1. 注目トピック",
        "## 2. 要約",
        "## 3. 実務への示唆",
        "## 4. 今日試すこと",
        "## 5. 深掘り候補",
        "",
    ]

    for topic in topics:
        lines.append(f"【テーマ】{topic['name']}")
        lines.append(f"【役割】{topic['role']}")
        for idx, item in enumerate(topic["items"], start=1):
            lines.append(f"- 記事{idx}")
            lines.append(f"  タイトル: {item['title']}")
            lines.append(f"  公開情報: {item['published']}")
            lines.append(f"  ソース: {item['source']}")
            lines.append(f"  要旨: {item['summary']}")
            lines.append(f"  URL: {item['link']}")
        lines.append("")

    return "\n".join(lines)


def generate_report(client: OpenAI, model: str, prompt: str) -> str:
    response = client.responses.create(
        model=model,
        input=prompt,
    )
    return response.output_text.strip()


def save_report(output_dir: Path, report: str) -> Path:
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    path = output_dir / f"morning_report_{stamp}.md"
    path.write_text(report, encoding="utf-8")
    return path


def notify(title: str, message: str) -> None:
    try:
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(["osascript", "-e", script], check=False)
    except Exception:
        pass


def send_gmail(report_path: Path, report_text: str) -> None:
    gmail_from = os.getenv("GMAIL_FROM", "").strip()
    gmail_to = os.getenv("GMAIL_TO", "").strip()
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()

    if not gmail_from or not gmail_to or not gmail_app_password:
        print("Gmail設定が未入力のため、メール送信をスキップしました。")
        return

    msg = EmailMessage()
    today = dt.datetime.now().strftime("%Y-%m-%d")
    msg["Subject"] = f"朝レポート {today}"
    msg["From"] = gmail_from
    msg["To"] = gmail_to

    body = f"""朝レポートを送ります。

保存ファイル:
{report_path}

--- 本文 ---
{report_text}
"""
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(gmail_from, gmail_app_password)
        server.send_message(msg)


def main() -> None:
    client, model, output_dir, source_topics = load_config()

    topics_with_items = []
    for topic in source_topics:
        items = collect_feed_items(topic["feeds"])
        topics_with_items.append({
            "name": topic["name"],
            "role": topic["role"],
            "items": items,
        })

    today = dt.datetime.now().strftime("%Y-%m-%d")
    prompt = build_prompt(topics_with_items, today)
    report = generate_report(client, model, prompt)
    path = save_report(output_dir, report)

    preview = f"朝レポートを保存しました: {path.name}"
    print(preview)
    notify("Morning Report", preview)
    send_gmail(path, report)


if __name__ == "__main__":
    main()