# Morning Report Starter

Mac向けの朝レポート自動化スターターです。

## できること
- Web検索で最新トピックを収集
- OpenAI Responses APIで日本語レポート化
- Markdown保存
- macOS通知
- launchdで毎朝6:00実行

## セットアップ
1. Python 3.10+ を用意
2. 仮想環境を作成
3. `pip install -r requirements.txt`
4. `.env.example` を `.env` にコピーして `OPENAI_API_KEY` を設定
5. `python morning_report.py` でテスト実行

## 今回の実装方針
- リサーチは公開RSS中心
- 要約と実務示唆はOpenAI API
- まずはローカル保存と通知
- メール送信は次段階で追加しやすい構造

## launchd
`com.yasu.morningreport.plist` を `~/Library/LaunchAgents/` に配置し、
パスを自分の環境に合わせて編集してから次を実行:

```bash
launchctl unload ~/Library/LaunchAgents/com.yasu.morningreport.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.yasu.morningreport.plist
launchctl start com.yasu.morningreport
```

## 注意
- Macがスリープ中なら、`launchd` の `StartCalendarInterval` ジョブは起床時に実行されます。電源オフ中は実行されません。
