# SMAI運用タスク一覧

| タスク | 実行 | 必須度 | 失敗時 |
|---|---|---:|---|
| SMAI Streamlit | `scripts/start_smai_server.bat` | 必須 | UI停止 |
| Server Watch | `scripts/server_ops/watch_smai_server.ps1` | 高 | 自動復旧停止 |
| Server Analytics | `run_dashboard.bat` | 高 | 監視画面停止、SMAI本体は継続 |
| Health Check | `run_health.bat` | 高 | 状態表示が古くなる |
| Symbol Maintenance | `scripts/run_symbol_maintenance_if_due.bat` | 中 | 銘柄マスター更新停止 |
| Notification Scheduler | `scripts/run_notification_scheduler.bat` | 任意 | 定時通知停止 |
| Assistant Gateway/Ollama | 本体設定に従う | 任意 | LLMのみ縮退 |

## データ境界

- `SMAI_Server_Analytics`: 監視コード、運用手順、保持ポリシー
- `SMAI_Server_Runtime`: ログ、バックアップ、状態、画面用snapshot。Git管理しない
- `Smart_Market_AI`: アプリ本体と正式な銘柄マスター
- 日付別importレポートとraw取得物は生成物としてGitへ自動追加しない

