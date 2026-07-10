# SMAI Server Analytics - Project Context

## Purpose

SMAI本体をWindows PC上で常時運用するための、独立した監視・バックアップ・障害解析プロジェクトです。

## Current status

- `dashboard.py`: Tkinterのデスクトップ監視画面。5秒間隔でhealth snapshot、session、operation、直近ログを更新
- `health.py`: L1 TCP/Streamlit health、L2ページ応答、L3 state/data read-writeの3段階確認
- `backup.py`: user data、server ops state、正式なsymbol universeをRuntimeへmanifest付きバックアップ
- `retention.py`: Runtimeログの保持期限処理
- `retention_policy.json`: ログ、バックアップ、生成レポート、Git追跡対象の方針
- `tasks.md`: SMAI本体と運用コンポーネントの責務一覧
- `audit.py`: secretを除外した操作イベントをRuntimeの`audit/events.jsonl`へ追記
- `dashboard.py`の`Activity History`: ユーザー、操作、対象、結果、端末擬似ID、所要時間を表示

## Runtime layout

既定値は次のとおりです。

```text
C:\Users\user\workspace\Smart_Market_AI       # SMAI本体
C:\Users\user\workspace\SMAI_Server_Analytics # このリポジトリ
C:\Users\user\workspace\SMAI_Server_Runtime   # ログ・バックアップ・実行状態
```

`SMAI_PROJECT_ROOT` と `SMAI_RUNTIME_ROOT` で変更できます。

## Explicit boundaries

- Analyticsは本体のランキング、Forecast、スコア、ユーザーデータを変更しない
- 監視画面停止はSMAI本体停止を意味しない
- Gateway/Ollama/通知schedulerは任意依存として表示する
- 生成レポートは障害調査用にRuntimeへ保存し、通常はGitへ追跡しない
- 再現性のある銘柄マスターとmanifestだけを本体側のGitで追跡する

## Next priorities

1. AnalyticsのWindowsタスク登録を追加
2. graceful shutdownの本体連携を実機確認
3. backup create/verify/restore smokeを追加
4. ログ容量上限・圧縮・エラー保持期間を実装
5. symbol maintenanceの自動pushをdry-runで確認後に有効化
6. SMAI本体のプロフィール選択、ページ操作、主要処理へ`audit.record_event`の連携
