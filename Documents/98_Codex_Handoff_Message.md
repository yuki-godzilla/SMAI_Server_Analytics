# SMAI Server Analytics 引継ぎメッセージ

作成日: 2026-07-11  
対象リポジトリ: `yuki-godzilla/SMAI_Server_Analytics`  
目的: SMAI本体の常時運用、監視、バックアップ、障害解析、操作履歴をAnalytics側で詳細開発する。

## 1. 最初に読むファイル

1. `AGENTS.md`
2. `PROJECT_CONTEXT.md`
3. `Documents/06_MVP_Operations_Guide.md`
4. `Documents/07_Server_Analytics_Screen_Design.md`
5. `tasks.md`
6. `Documents/99_Work_Log.md`

## 2. リポジトリとRuntimeの位置

現在の想定構成は次のとおり。

```text
C:\Users\user\workspace\SMAI_Projects\
├─ Smart_Market_AI        # SMAI本体
├─ SMAI_Server_Analytics  # このリポジトリ
└─ SMAI_Server_Runtime    # ログ、監査履歴、状態、バックアップ
```

`SMAI_PROJECT_ROOT` と `SMAI_RUNTIME_ROOT` で上書き可能。通常のAnalytics起動batは新しい階層を既定値にしている。

## 3. 現在の実装済み機能

### Analytics UI

`dashboard.py` は外部依存のないTkinterデスクトップ画面。

- `Overview`: L1〜L3 health、overall、セッション数、処理数
- `Sessions`: セッションID、heartbeat、状態
- `Activity History`: 監査イベント一覧、結果フィルタ
- `Incidents`: failed/error/criticalイベント
- `Tasks`: Windows Scheduled Taskの状態とLast Result
- `Logs`: server_ops / maintenance / healthの直近ログ

画面は5秒ごとに更新する。SMAI本体が停止していても、Analytics画面自体は最後のsnapshotとログを表示できる。

### Health

`health.py` の確認レベルは以下。

- L1: TCP 8501、Streamlit `/_stcore/health`
- L2: Streamlitトップページ応答
- L3: server ops state / user dataの読み書き

L1失敗は`critical`、L2/L3のみの失敗は`degraded`、全成功は`healthy`。snapshotは本体の`data/ops/server_ops/health_snapshot.json`、履歴はRuntimeへ保存する。

### Backup / retention

- `backup.py`: user data、server ops state、正式な銘柄マスターをmanifest付きでRuntimeへ保存
- `retention.py`: Runtimeログの保持期限処理
- `retention_policy.json`: 保持日数とGit追跡対象を定義

日付別reports、raw HTML、ログ、再生成可能cacheはGitへ自動追加しない。正式なsymbol universe、source CSV、manifestはSMAI本体リポジトリ側の対象とする。

### Audit

`audit.py` の`record_event()`がRuntimeの`audit/events.jsonl`へイベントを書き込む。

標準項目:

```text
timestamp, user_id, action, target, result,
device_id, platform, duration_ms
```

`device_id`はRuntime固有saltと端末情報から生成する擬似ID。token、secret、password、topic、inputはmetadataから除外する。

## 4. 未完了の最重要作業

### A. SMAI本体から監査イベントを送る

現在はAnalytics側のイベント記録・表示基盤のみ。SMAI本体の以下へ連携フックを追加する必要がある。

- プロフィール選択 / ログイン
- ログアウト / ユーザー切替
- ページ遷移
- ランキング作成
- 銘柄データ取得
- AI調査
- レポート生成
- 設定変更
- 成功 / 失敗 / キャンセル

AnalyticsがSMAI本体のprivate moduleをimportする構成は禁止。連携は、安定したJSONL契約、CLI、または本体側の小さなadapterを使用する。

### B. Sessionsの端末情報を充実させる

現状のSessionsタブはactivity stateのsessionとheartbeatを表示する。次の項目を本体側から追加する。

- user_id
- profile display name
- login_at
- last_seen_at
- device_id
- browser / OSの限定的な情報
- connection state

IPアドレスは識別子にしない。User-Agentや端末情報は診断に必要な最小限だけ保存する。

### C. Windowsタスクを新物理パスへ再登録する

AnalyticsとRuntimeは新階層へ物理移動済み。本体は、8501を占有するSession 0の孤立Pythonプロセスにより物理移動ができず、現在は次のJunctionで互換性を維持している。

```text
C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI
    -> C:\Users\user\workspace\Smart_Market_AI
```

Windows再起動などで8501プロセスが解放された後に、次を行う。

1. Junctionであることを確認
2. Junctionだけを削除
3. `Smart_Market_AI`本体を`SMAI_Projects`配下へ物理移動
4. 管理者PowerShellでタスク再登録

```powershell
cd C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI
.\scripts\server_ops\register_smai_autostart_task.ps1
.\scripts\register_symbol_maintenance_if_due_task.ps1
```

対象タスク:

- `SmartMarketAI-Server-Autostart`
- `SmartMarketAI-Server-Watch`
- `SmartMarketAI-Symbol-Maintenance-IfDue`

旧`SmartMarketAI-LAN-Server`は無効化済み。

### D. 段階停止の実機確認

`scripts/stop_smai_server.bat` は停止要求ファイルを作成してから通常停止を試み、30秒後に必要ならforce停止する仕様。SMAI本体が新パスへ移動した後、実機で以下を確認する。

- 実行中のランキングや書き込みを待って停止する
- resilient launcherが停止要求を認識する
- 30秒timeout時だけforce停止する
- SQLite / JSON / cacheの破損がない
- Watcherが意図した手動停止を復旧扱いしない

## 5. 銘柄更新の自動commit/push方針

SMAI本体の`tools/auto_commit_symbol_updates.py`が許可対象を限定する。

自動commit/push対象:

- `data/marketdata/symbol_universe.csv`
- `data/marketdata/symbol_universe_sources/*.csv`
- `data/marketdata/*manifest*.json`

対象外:

- raw HTML
- reports
- logs
- runtime cache
- user data
- temporary files

許可外の差分がある場合はfail-closedで停止する。自動push失敗を成功扱いしない。secret検査と`git diff --cached --check`をpush前に追加するのが次の改善。

## 6. 検証コマンド

Analytics側:

```powershell
cd C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Analytics
$env:PYTHONDONTWRITEBYTECODE = "1"
..\Smart_Market_AI\venv_SMAI\Scripts\python.exe -m py_compile dashboard.py audit.py health.py backup.py retention.py
..\Smart_Market_AI\venv_SMAI\Scripts\python.exe health.py
git status --short
```

本体側のtargeted check:

```powershell
cd C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI
.\venv_SMAI\Scripts\python.exe -m pytest tests/test_server_operations_scripts.py tests/test_server_ops_launcher.py tests/test_server_ops_maintenance.py tests/test_server_ops_scripts.py tests/test_lan_server_script.py -q
```

注意: 管理者権限で作成されたpytest temp/cacheは通常ユーザーからPermissionErrorになることがある。権限を混在させず、必要なら管理者環境で再実行する。

## 7. 直近commit

Analytics:

```text
9137bec feat: design and expand server analytics console
86ce2c9 chore: align analytics paths with SMAI_Projects
```

SMAI本体:

```text
5ae8dd9 chore: normalize SMAI workspace references
ce08ebf chore: stop tracking generated reports and raw imports
```

## 8. 重要な注意

- `git add .`は禁止。対象ファイルを明示する。
- SMAI本体とAnalyticsのGit操作を必ず別々の絶対作業ディレクトリで行う。
- Reports/raw/log/cacheを誤って本体Gitへ追加しない。
- Runtimeにはユーザー・端末・操作情報が含まれるためGit管理しない。
- 投資スコア、ランキング、Forecast、Decision Reportの意味をAnalytics側で変更しない。
- 実行していない確認を実行済みと報告しない。

## 9. 次の推奨順序

1. Windows再起動後に本体の物理移動とScheduled Task再登録
2. SMAI本体のログイン / 操作イベント連携
3. Sessionsの端末・profile表示強化
4. Activity Historyの期間、ユーザー、操作、結果フィルタ
5. Incidentsのseverity分類と障害相関表示
6. backup verify / restore smoke
7. 自動push前のsecret検査とdry-run

