# SMAI Server Analytics 運用ガイド

## 1. 運用モデル

SMAI本体、Analytics画面、Runtimeデータを分離します。SMAI本体は `Smart_Market_AI`、監視画面と診断コードは `SMAI_Server_Analytics`、ログとバックアップは `SMAI_Server_Runtime` に置きます。

画面はPC上で `run_analytics_web.bat` を起動します。SMAIが停止しても、最後に取得した状態と直近ログを確認できます。Web ConsoleはTCP 8502で待ち受け、Tailscale MagicDNSによりLAN内・外出先の管理端末から同じURLで確認できます。

### MagicDNSによる管理端末からの閲覧

PC、タブレット、スマートフォンから同じ運用状態を確認する場合は、Analyticsプロジェクトで`run_analytics_web.bat`を実行します。SMAI本体のStreamlitとは別のTCP 8502で、読み取り専用のOperations Consoleを起動します。管理端末ではTailscaleを起動し、LAN内でも外出先でも`http://smai-server:8502`を開いてください。Main Applicationは`http://smai-server:8501`であり、同じサーバー名と異なるポート番号で区別します。サーバーPC内の確認だけは`http://localhost:8502`を使用します。Web Consoleだけを再起動する場合は`restart_analytics_web.bat`を使用します。

- ブラウザー画面は5秒ごとに状態を更新し、L1〜L3のhealth snapshot、セッション、タスク、障害、直近ログを表示します。
- この画面はSMAI本体の計算、ランキング、スコア、Forecast、ユーザーデータ、タスク設定を変更しません。
- TCP 8502をインターネットへ公開しません。ルーターのポート開放、Tailscale Funnel、UPnPは使用しません。Firewall変更は自動で行わず、必要な場合だけAnalytics TCP 8502がMain TCP 8501と別ルールであり、パブリックネットワークを許可しないことを確認します。
- URL設定は`config/network.json`に集約します。端末名を変更する場合は本体の`config/server.yaml`と同じ`tailscale_hostname`に更新するか、両方の起動環境で`SMAI_TAILSCALE_HOSTNAME`を設定します。旧LAN IP／Tailscale IPの通常案内は廃止しました。
- Analyticsにはアプリ内の追加認証はありません。到達可能なTailnet参加者は閲覧できるため、Tailnetの参加者とACLを運用者に限定します。より細かな認証・認可は別途設計します。

接続できない場合は、次を順に確認します。

1. 接続端末でTailscaleが起動している
2. SMAIサーバーPCが起動している
3. Server Analyticsが起動している
4. `http://smai-server:8502`とポート番号が正しい
5. Windows FirewallがAnalytics TCP 8502を遮断していない

## 2. ヘルスチェック

`run_health.bat` は次を記録します。

- L1: TCP 8501、Streamlit `/_stcore/health`
- L2: Streamlitトップページ応答、Tailscale adapter
- L3: `data/ops/server_ops` と `data/user` の読み書き、物理ディスク、空きメモリ、CPU、過去24時間の異常停止

L1失敗は `critical`、L2/L3の失敗・不明は `degraded`、全成功は `healthy` です。snapshotは本体の `data/ops/server_ops/health_snapshot.json`、履歴はRuntimeのhealth logへ保存します。

### 5分ホスト監視

`SMAI-Host-Monitor`は5分タスクとして`health.py`を実行します。管理者コンテキストではSYSTEM、非管理者コンテキストでは現在の対話ユーザーで登録します。どちらも画面閲覧には依存しませんが、非管理者登録はログオン中だけ実行されます。Windowsの異常停止イベント、Tailscale、メモリ、CPU、物理ディスクに異常があっても、監視タスクはWindows再起動・サービス停止・外部送信を行いません。`SMAI-Host-Monitor`は最終成功から10分超を`degraded`、20分超を`critical`として表示します。

### 推移・容量・復旧可能性

`推移`画面は、5分単位に集計したL1〜L3の状態履歴、Streamlit health/page応答のp95、SMAIデータとRuntimeの空き容量を表示します。画面を再起動しても履歴は失われません。過去24時間、7日、30日を選択でき、観測が欠けた時間帯は正常率へ加えず灰色の`unknown`として表示します。

healthの生記録は `Runtime/logs/health/YYYY-MM-DD.jsonl` に日別保存し、調査用に2日間保持します。画面用の5分集計は `Runtime/metrics/health/YYYY-MM-DD.jsonl` に30日間保持します。Retentionは両方を期限に従って削除します。

Overviewの`Recovery Readiness`は、`backup.py smoke` が記録した最終隔離復元検証、最小空き容量、選択中期間の履歴カバレッジを示します。記録がない・読めない場合は成功と推測せず`unknown`として扱います。

### タスク実行鮮度

`タスク`画面は、Windows Task Schedulerから取得した最終実行時刻、次回予定、最終結果、実行パスの一致判定を確認します。絶対実行パスやコマンド引数は画面へ表示しません。状態はRuntimeの `metrics/tasks/YYYY-MM-DD.jsonl` に、状態変化または5分間隔で保存され、`推移`画面の`JOB FRESHNESS`に表示されます。

- `SMAI-Incident-Automation` は5分ごとの想定に対して、最終成功から10分超を`degraded`、20分超を`critical`とします。
- `SMAI-Host-Monitor` は5分ごとの想定に対して、最終成功から10分超を`degraded`、20分超を`critical`とします。
- `Backup Restore Smoke` は月次検証を前提に、31日超を`degraded`、35日超を`critical`とします。
- At logon／At startupのタスクは前回起動時刻の古さだけで異常としません。ただし、最終結果が非ゼロ、タスク無効、実行パス不一致、取得不能は正常扱いしません。
- タスク未登録、権限不足、Scheduler出力を解釈できない場合は`unknown`です。自動再起動や自動修正は行いません。

### クライアント通信の確認

OverviewのService Topologyでは、PCブラウザ、スマートフォン、タブレットとStreamlitの各経路を確認できます。これは端末に対する外向きpingではなく、SMAIが受信したセッションheartbeatの鮮度を確認する仕組みです。90秒以内のheartbeatを`ok`、90秒超過または明示的な切断を`degraded`、明示的な失敗を`critical`として表示します。

端末種別ごとの通信証跡がない場合、端末種別が未送信の場合、または`activity_state.json`を読み取れない場合は`unknown`です。利用者がいないことを障害と推測せず、証跡がないことを正常とも扱いません。保存対象は`desktop`、`smartphone`、`tablet`の種別と最終通信・接続状態だけであり、生のUser-Agent、IPアドレス、Cookieは記録しません。

### 接続数・接続履歴

Sessions画面の上段では、PC、スマートフォン、タブレットごとに、90秒以内のheartbeatを根拠にした現在接続数を表示します。累計はAnalyticsが監視を開始してから確認した`device_id`（Runtime固有saltによる擬似ID）だけを数えます。`device_id`が未連携のセッションは推測で台数へ加えず、`ID未連携`として表示します。

接続観測の履歴はRuntimeの`connections/watch_state.json`に保存します。初回観測、状態変化、監視対象からの消失を記録しますが、セッションがファイルから消えたことを切断と断定しません。状態ファイルが破損・読み取り不能の場合は履歴と累計を`unknown`として扱い、空の正常値に置き換えません。

## 3. バックアップと復元

`run_backup.bat` はRuntimeの `backups/` にmanifest付きバックアップを作成します。対象はユーザーデータ、運用状態、正式な銘柄マスターです。

日付別レポート、raw HTML、ログ、再生成可能なcacheはバックアップ対象外です。バックアップ作成後はmanifestのSHA-256を検証し、月1回は別フォルダへ復元する実地確認を行います。

復元はmanifest、全ファイルのSHA-256、パスの逸脱を確認してから開始します。1件でも破損、欠落、コピー未完了（`skipped`）があれば、復元先へ書き込みません。通常の実地確認は本体を上書きせず、隔離先へ行います。

```powershell
python .\backup.py verify <backup-path>
python .\backup.py restore <backup-path> --destination <isolated-restore-directory>

# 作成・検証・隔離先復元・復元物のhash照合を一度に行う
python .\backup.py smoke
```

本体データへの復元は、隔離先で内容とhashを確認した後に、対象と上書き範囲を明示して実施します。

`smoke` は本体データを上書きしません。Runtime配下の一時ディレクトリへ復元して削除し、結果を `backup_restore_smoke.json` と `logs/backup_restore_smoke.log` に記録します。バックアップ作成、manifest検証、復元、復元物のhash照合、結果記録のいずれかが失敗した場合は `critical` として終了します。

## 4. PC常時運用と安全な週次保守

最初に`capture_smai_host_baseline.ps1`を実行し、Runtimeの`host_maintenance/baselines/`へ電源設定、Windows UpdateのActive Hours、旧`WeeklyRestart`を含む関連タスクXMLを保存します。RuntimeはGit管理しません。

`SMAI-Host-Maintenance`は日曜04:00に実行します。旧`WeeklyRestart`の`Restart-Computer -Force`とは異なり、次の条件をすべて満たす場合だけ再起動を要求します。

1. 15分以内に確認されたSMAIセッションがない
2. 実行中のSMAI操作がない
3. 10分以内の`healthy` health snapshotがある
4. 直前バックアップの作成と検証が成功する
5. retentionが成功する

条件を満たさない場合は`deferred`をRuntimeへ記録して正常終了し、Windows再起動を要求しません。最初の確認では必ず`invoke_smai_host_maintenance.ps1 -DryRun`を使います。再起動なしでバックアップとretentionまで確認する場合は`-NoRestart`を使います。

```powershell
.\scripts\invoke_smai_host_maintenance.ps1 -DryRun
.\scripts\invoke_smai_host_maintenance.ps1 -NoRestart
```

新タスクへの切替は、登録後のtask XML・dry-run・health結果を確認してから行います。

```powershell
.\scripts\register_smai_host_maintenance_task.ps1 -ReplaceLegacyWeeklyRestart
```

  この切替は旧タスクを削除せず無効化するだけです。`WeeklyRestart`を操作できる管理者として開いたPowerShellで実行し、非昇格の実行ではタスクを変更せず停止します。ロールバック時も同じく管理者PowerShellで次を実行します。

```powershell
.\scripts\unregister_smai_host_maintenance_task.ps1 -RestoreLegacyWeeklyRestart
.\scripts\restore_smai_server_power_profile.ps1
```

  PC設定は管理者として開いたPowerShellで`set_smai_server_power_profile.ps1 -Apply`を実行すると、バランス電源プランを維持したままAC時Hybrid SleepとFast Startupを無効にし、AC時スリープ・休止状態を無効にします。Windows UpdateのActive Hoursは08:00〜02:00へ設定し、日曜04:00を保守枠にします。実行前の値はbaselineで確認でき、BIOS・Firewall・ネットワーク設定は変更しません。非昇格では設定を一部だけ変えることなく停止します。

### ログオン時のプロンプトとWeb画面

SMAI Main Applicationは既存のWindows起動タスクでサーバープロセスを維持します。AnalyticsはTCP 8502のhealth endpointを先に確認し、すでに正常であれば二重起動せず終了します。ログオン時の起動と表示は、管理者権限が不要な現在のユーザーのWindows Startupフォルダーへ登録します。Analyticsは45秒待機してから同じ確認を行うため、既存の`SMAI-Server-Analytics`が残っていても二重起動しません。

`SMAI-Operations-Workspace`はログオン時に、Main Application用とAnalytics用のPowerShellプロンプトをそれぞれ開きます。各プロンプトは30秒ごとにlocalhostのhealth endpointを確認するだけで、サーバープロセスを起動・停止しません。両サービスが応答できた時点で、既定ブラウザーに`http://localhost:8501`と`http://localhost:8502`を開きます。サーバーの起動途中は最大180秒待機し、応答できないサービスのページは開きません。

```powershell
.\scripts\register_smai_analytics_autostart_task.ps1
.\scripts\register_smai_operations_workspace_task.ps1 -RunImmediately
```

プロンプトを閉じてもサーバーは停止しません。不要になった場合は、ユーザータスクだけを次で削除できます。

```powershell
.\scripts\unregister_smai_operations_workspace_task.ps1
```

## 5. ログ保持

通常ログ、healthの5分集計、タスク鮮度履歴は30日、health生記録は2日、障害ログは90日を基準とします。RuntimeはGit管理しません。ログにはsecret、通知topic、token、Cookie、ユーザー入力本文を記録しません。

## 6. 銘柄更新とGit

銘柄更新成功後に限り、本体側の限定された成果物をcommit/pushします。

- 追跡: `symbol_universe.csv`、source CSV、manifest JSON
- 非追跡: raw取得物、実行ログ、cache、日付別レポート、ユーザーデータ

許可外の差分がある場合はfail-closedで自動pushを停止します。

## 7. 障害対応

1. Analytics画面のoverallと最終確認時刻を見る
2. L1/L2/L3のどの層が失敗したかを確認する
3. `SMAI_Server_Runtime/logs` と本体のserver_opsログを確認する
4. 実行中処理・session・lockを確認する
5. 処理中でなければ段階停止を実行する
6. 復旧後にhealthとバックアップ検証を再実行する

## 8. 操作履歴と端末情報

AnalyticsのActivity Historyは、Runtimeの`audit/events.jsonl`を読み取ります。イベントにはUTC時刻、ユーザーID、操作名、対象、結果、所要時間、端末擬似ID、OSが含まれます。

端末擬似IDはRuntime固有のsaltと端末情報から生成し、IPアドレスを識別子にしません。token、secret、password、通知topic、入力本文はイベントへ保存しません。イベントログ自体はユーザー情報を含むため、RuntimeをGitへcommitせず、保持期限とバックアップ対象を明示して管理します。

SMAI本体は、次の操作を同じJSONL契約でRuntimeへ記録します。

- プロフィール開始・セッション解除・ユーザー切替
- 画面遷移（同一画面のStreamlit再実行は記録しない）
- コックピットの市場データ取得
- ランキング作成
- Copilotから実行するデータ取得・AI調査・レポート作成などの確認済み操作

記録処理はbest-effortです。Runtimeへの書き込みに失敗しても本体の利用操作を失敗扱いにせず、失敗は本体ログで追跡します。イベントmetadataにはtoken、secret、password、通知topic、入力本文を保存しません。
