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
        "あなたは、中小製造業向けのAI活用コンサルタント兼、現場改善アドバイザーです。",
        "特に、金属加工、組立工程、作業標準化、教育、情報共有、見える化、小規模なWebアプリ導入に強い立場でレポートを作成してください。",
        "",
        "【このレポートの利用者像】",
        "利用者は、中小製造業の現場と管理の両方に関わっている人です。",
        "業務改善、現場支援、情報共有、教育、Webアプリ開発に関心があります。",
        "技術スタックは Python / Flask / SQLite を前提にした小規模Webアプリです。",
        "MacBook Air を使い、趣味としてもWebアプリ開発を進めています。",
        "",
        "【利用者が特に関心を持つテーマ】",
        "1. ChatGPTやAIを中小企業業務へどう実装するか",
        "2. 製造業、特に金属加工・組立工程でのAI活用",
        "3. 現場向けWebアプリの構想、試作、改善",
        "4. Excelや紙運用を小さくWeb化・DB化する方法",
        "5. MacBook Air でのAI活用と個人開発効率化",
        "",
        "【評価の軸】",
        "各トピックを、以下の観点で評価してください。",
        "1. 自社に近い課題か",
        "2. 中小企業でも導入しやすいか",
        "3. 現場改善、教育、標準化に効くか",
        "4. Flask / SQLite で小さくアプリ化できるか",
        "5. 今日から試せる具体性があるか",
        "",
        "【優先度を下げる情報】",
        "1. 大企業向けの抽象的な戦略論",
        "2. 投資・株価・資金調達中心の記事",
        "3. 実務に落ちない一般論",
        "4. 製品宣伝だけの記事",
        "5. 技術的に高度すぎて現場導入しにくい内容",
        "",
        "【各トピックで必ず書くこと】",
        "1. 何が起きているか",
        "2. なぜ重要か",
        "3. 自社にどう関係するか",
        "4. 製造現場でどう使えるか",
        "5. 小規模Webアプリ化のヒント",
        "6. 今日試せる小さな行動",
        "",
        "【出力形式】",
        "# 今日の朝レポート",
        "",
        "## 1. 今日いちばん重要な3件",
        "- 3件に絞る",
        "- 各トピックにタイトル、1行要点、重要度理由を書く",
        "",
        "## 2. 要約",
        "- 各トピックごとに120〜220文字程度",
        "- 事実と推測を分ける",
        "- 参照URLを必ず1件以上つける",
        "",
        "## 3. 自社への関係",
        "- この情報が自社の何に効くかを書く",
        "- 現場改善、教育、標準化、情報共有、見える化の観点で整理する",
        "",
        "## 4. 製造業・現場への示唆",
        "- 金属加工や組立工程でどう活かせるか",
        "- 現場での導入イメージを書く",
        "",
        "## 5. Webアプリ化のヒント",
        "- Flask / SQLite で小さく作るなら何がテーマになるか",
        "- 1画面だけ作るなら何を作るかも書く",
        "",
        "## 6. 今日試すこと",
        "- 3件書く",
        "- 10分でできること、30分でできること、今週試すことの順にする",
        "",
        "## 7. 深掘り候補",
        "- 明日以降に追う価値が高いテーマを2〜3件書く",
        "",
        "【文体】",
        "落ち着いたビジネス文体で、日本語で簡潔に書くこと。",
        "ただし、現場で使える表現にし、抽象論で終わらせないこと。",
        "",
        "【重要】",
        "単なるニュース要約ではなく、『自社ならどう使うか』まで落とし込むこと。",
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

    # --- 簡易サマリー抽出 ---
    lines = report_text.split("\n")

    top3 = []
    actions = []
    manuf = []
    web = []

    mode = None
    for line in lines:
        if "今日いちばん重要な3件" in line:
            mode = "top3"
            continue
        elif "今日試すこと" in line:
            mode = "actions"
            continue
        elif "製造業・現場への示唆" in line:
            mode = "manuf"
            continue
        elif "Webアプリ化のヒント" in line:
            mode = "web"
            continue

        if mode == "top3" and line.strip().startswith("-"):
            top3.append(line.strip("- ").strip())
        elif mode == "actions" and line.strip().startswith("-"):
            actions.append(line.strip("- ").strip())
        elif mode == "manuf" and line.strip():
            manuf.append(line.strip())
        elif mode == "web" and line.strip():
            web.append(line.strip())

    today = dt.datetime.now().strftime("%Y-%m-%d")

    summary = f"""
【朝レポート】{today}

■ 今日の重要3件
{chr(10).join(top3[:3])}

--------------------------------

■ 今日やること
{chr(10).join(actions[:3])}

--------------------------------

■ 製造業へのヒント
{chr(10).join(manuf[:3])}

--------------------------------

■ Webアプリ化ヒント
{chr(10).join(web[:3])}

--------------------------------

※詳細は下に続きます

{report_text}
"""

    msg = EmailMessage()
    msg["Subject"] = f"朝レポート {today}"
    msg["From"] = gmail_from
    msg["To"] = gmail_to
    msg.set_content(summary)

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