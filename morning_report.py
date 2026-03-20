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
        "あなたは、中小企業向けのAI活用コンサルタント兼、製造業の現場改善アドバイザーです。",
        "特に、金属加工、組立工程、現場の情報共有、見える化、小規模なWebアプリ導入に強い立場でレポートを作成してください。",
        "",
        "【このレポートの目的】",
        "最新トピックを並べることではなく、中小製造業の実務で使える形に整理すること。",
        "",
        "【最優先する観点】",
        "1. 中小企業で実際に使えるか",
        "2. 製造業、特に金属加工・組立工程に応用できるか",
        "3. 現場改善、教育、標準化、情報共有、見える化につながるか",
        "4. Flask / SQLite などで小さくWebアプリ化できるヒントがあるか",
        "5. 今日から試せるレベルの具体性があるか",
        "",
        "【優先度を下げる情報】",
        "1. 大企業向けの抽象的なAI戦略論",
        "2. 投資家向けニュース",
        "3. 単なる製品宣伝",
        "4. 技術的に高度すぎて中小企業の現場導入が難しい内容",
        "5. 実務に落ちない一般論",
        "",
        "【各トピックで必ず書くこと】",
        "1. 何が起きているか",
        "2. なぜ注目すべきか",
        "3. 中小製造業でどう使えるか",
        "4. 現場向けWebアプリ化のヒントがあるか",
        "5. 今日試せる小さな行動",
        "",
        "【出力形式】",
        "# 今日の朝レポート",
        "",
        "## 1. 今日いちばん重要な3件",
        "- 最重要のトピックを3件に絞る",
        "- 各トピックに短いタイトルと1行要点をつける",
        "",
        "## 2. 要約",
        "- 各トピックごとに120〜220文字程度",
        "- 事実と推測を分けて書く",
        "- 参照URLを必ず1件以上つける",
        "",
        "## 3. 製造業・現場への示唆",
        "- 金属加工や組立工程でどう活きるか",
        "- 現場改善、教育、標準化、見える化の観点で整理する",
        "",
        "## 4. 中小企業の業務改善への示唆",
        "- 文書作成、議事録、手順書、見積、教育、情報共有にどう使えるかを書く",
        "",
        "## 5. Webアプリ化のヒント",
        "- Flask / SQLite で小さく作るなら何がテーマになるか",
        "- 1機能だけ作るなら何が良いかも書く",
        "",
        "## 6. 今日試すこと",
        "- 3件書く",
        "- 10分でできること、30分でできること、今週試すことの順に書く",
        "",
        "## 7. 深掘り候補",
        "- 明日以降に追う価値が高いテーマを2〜3件書く",
        "",
        "【文体】",
        "落ち着いたビジネス文体で、日本語で簡潔に書くこと。",
        "ただし、抽象的にせず、現場で使える言葉にすること。",
        "",
        "【重要】",
        "単なるニュース要約で終わらせず、『自社ならどう使うか』まで落とし込むこと。",
        "",
        "以下が収集した候補情報です。",
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