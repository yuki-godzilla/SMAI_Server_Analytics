# SMAI Server Analytics

SMAI本体を安全に常時運用するための、ローカルファーストな監視・バックアップ・障害解析プロジェクトです。正規の画面は、PC・タブレット・スマートフォンから同じ状態を確認できる読み取り専用のWeb Operations Consoleです。本リポジトリはSMAI本体の投資計算、ランキング、Forecast、ユーザー画面を所有しません。

## Web Operations Console

セットアップ後、次のランチャーで起動します。

```powershell
.\run_analytics_web.bat
```

通常の接続先はMagicDNSで統一します。Main Applicationと同じサーバー名を使い、アプリはポート番号で区別します。

```text
Main Application:    http://smai-server:8501
Server Analytics:    http://smai-server:8502
サーバーPC内の確認: http://localhost:8502
```

LAN内でも外出先でも、管理端末でTailscaleを起動して`http://smai-server:8502`を開いてください。起動時表示と画面上の案内もこのURLだけを通常案内とし、LAN IP・Tailscale IPは障害調査時を除き表示しません。URL設定は非秘匿の[`config/network.json`](config/network.json)へ集約しており、端末名を変更する場合は本体の`config/server.yaml`と同じ値へ更新します。明示的な環境変数`SMAI_TAILSCALE_HOSTNAME`、`SMAI_ANALYTICS_PORT`、`SMAI_ANALYTICS_SCHEME`も使用できます。

- サマリーは5秒ごと、現在表示している画面だけは7秒ごとに部分更新します。データ収集とローカルhealth probeは15秒の共有キャッシュを使うため、非表示の画面を含む一斉再描画や接続端末ごとの重複したprobeは行いません。
- Overviewにはhealth score、現在状態、サービス概要、次に確認すべき画面への導線を表示します。詳細なhealth timelineとL1〜L3 check matrixは`推移`、Recovery Readinessは`改善レポート`で確認します。
- 異常、欠損、読み取り不能は正常扱いにせず、`degraded`、`critical`、`unknown`として表示します。
- SMAIの計算、ランキング、Forecast、ユーザーデータ、タスク設定を変更しません。
- TCP 8502をインターネットへ公開しません。ルーターのポート開放、Tailscale Funnel、UPnPは使用しません。Firewallの変更は自動化せず、必要な場合だけAnalyticsポートをMainポートと別ルールにし、パブリックネットワークを許可しないことを確認してください。
- Analyticsにアプリ内ログインはありません。到達可能なTailnet参加者は画面を閲覧できるため、Tailnetのメンバー・ACLを運用者へ限定してください。より細かな権限分離は今後の課題です。

Web Consoleだけを再起動するには、次を実行します。SMAI本体のStreamlitは停止しません。

```powershell
.\restart_analytics_web.bat
```

### iPhone / iPadでホーム画面へ追加する場合

Web Consoleは、ホーム画面用に`SMAI Analytics`のアプリアイコン（iPhone向け180px、PWA向け192px・512px）を配信します。更新後はSafariでConsoleを一度再読み込みし、以前作成した空白アイコンのショートカットを削除してから、共有メニューの**ホーム画面に追加**で作り直してください。iOSは既存ショートカットのアイコンを強くキャッシュします。

画面幅はSMAI本体と同じく、スマートフォン（767px以下）、タブレット（768〜1024px）、PC（1025px以上）を基準に調整しています。タブは横スクロール、更新ボタンは44px以上のタップ領域を維持します。

常時運用では、対話ユーザーのログオン後にWeb Consoleを起動するタスクを登録します。

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\register_smai_analytics_autostart_task.ps1
```

解除は次のとおりです。

```powershell
.\scripts\unregister_smai_analytics_autostart_task.ps1
```

## PC常時運用と安全保守

`SMAI-Host-Monitor`は5分ごとに、Main Application、Tailscale、物理ディスク、メモリ、CPU、過去24時間の異常停止を同じhealth snapshotへ記録します。さらにニュース更新と銘柄データ更新の最終成功時刻・連続失敗回数を確認し、24時間超の遅延は`degraded`、48時間超または連続4回失敗は`critical`として扱います。状態ファイルが欠損・破損している場合は`unknown`であり、正常とは表示しません。異常の記録だけでWindows全体を再起動することはありません。
NVIDIA GPUがあるPCでは、同じsnapshotへ温度・ファン・消費電力を任意のL3観測として記録します。GPUがない、または取得できないPCでは既存のhealth判定を悪化させません。タスク状態もこの監視で5分ごとに記録するため、Web Consoleを開いていない時間帯も履歴が残ります。

最初に変更前の電源・更新・タスク設定をRuntimeへ保存します。

```powershell
.\scripts\capture_smai_host_baseline.ps1
.\scripts\register_smai_host_monitor_task.ps1 -RunImmediately
.\scripts\register_smai_runtime_retention_task.ps1
```

週次の安全保守は、アクティブなSMAIセッション、実行中操作、古いhealth snapshot、health異常のいずれかを検知すると再起動を延期します。dry-runではバックアップ、保持期間削除、再起動を行いません。`WeeklyRestart`の置換は、二重実行を避けるため**管理者として開いたPowerShell**からだけ許可します。

```powershell
.\scripts\invoke_smai_host_maintenance.ps1 -DryRun
.\scripts\register_smai_host_maintenance_task.ps1 -ReplaceLegacyWeeklyRestart
```

新タスクは日曜04:00に、事前バックアップとretentionを成功させた後だけ、`-Force`なしで120秒後のWindows再起動を要求します。必要なら、猶予時間内に`shutdown /a`で中止できます。旧`WeeklyRestart`は削除せず無効化するため、ロールバックできます。

```powershell
.\scripts\unregister_smai_host_maintenance_task.ps1 -RestoreLegacyWeeklyRestart
.\scripts\unregister_smai_host_monitor_task.ps1
.\scripts\unregister_smai_runtime_retention_task.ps1
.\scripts\restore_smai_server_power_profile.ps1
```

電源設定は新規機器なしで適用できます。既定のdry-runを確認してから、**管理者として開いたPowerShell**でAC時Hybrid SleepとFast Startupを無効にし、Windows UpdateのActive Hoursを08:00〜02:00に設定します。バランス電源プラン、AC時スリープ無効、NVMeのWindows最適化は維持します。

```powershell
.\scripts\set_smai_server_power_profile.ps1
.\scripts\set_smai_server_power_profile.ps1 -Apply
```

## ログオン時の運用プロンプトとWeb画面

SMAI Main Applicationは既存のWindows起動タスクで起動を維持し、Analyticsはログオン時に重複を検出して起動します。ログオン時の自動起動は、管理者権限を必要としない現在のユーザーのWindows Startupフォルダーへ登録します。Analyticsは45秒待機してから確認するため、既存タスクが残っていても二重起動しません。`SMAI-Operations-Workspace`は同じログオン時に、既存プロセスを二重起動せず、MainとAnalyticsそれぞれの状態確認用PowerShellプロンプトを表示します。両方のhealth endpointが応答した後、既定ブラウザーで`http://localhost:8501`と`http://localhost:8502`を開きます。

```powershell
.\scripts\register_smai_analytics_autostart_task.ps1
.\scripts\register_smai_operations_workspace_task.ps1 -RunImmediately
```

プロンプトを閉じてもサーバープロセスは停止しません。Web画面を開き直すだけなら`open_smai_service_pages.ps1`を実行します。元に戻す場合は次を実行します。

```powershell
.\scripts\unregister_smai_operations_workspace_task.ps1
```

## 固定Gmail障害通知

critical障害の固定Gmail通知は初期状態で無効です。Googleアカウントで2段階認証と`SMAI Analytics Alerts`用のアプリパスワードを作成した後、対話中のWindowsユーザーで次を一度だけ実行します。

```powershell
.\scripts\configure_gmail_notifications.ps1
```

GmailアドレスはRuntimeのGit管理外設定、アプリパスワードはWindows Credential Managerだけへ保存されます。設定後、明示操作で最小のテスト通知を送れます。

```powershell
.\scripts\test_gmail_notifications.ps1
```

Analytics画面は読み取り専用のまま、Gmail通知の設定状態と最終配送結果だけを表示します。詳細な手順は[`Documents/08_Incident_Automation_Operations.md`](Documents/08_Incident_Automation_Operations.md)を参照してください。

## 承認制Codex Autofix

critical Incidentは通知だけでCodexを起動しません。第1承認後に隔離worktreeで修復commitを作り、第2承認後にcleanなAnalytics checkoutへfast-forwardします。マージレポートを管理者へ通知し、同じ40桁commit hashへの第3承認がある場合だけ、別の配備executorが利用状況・health・Git・backupを検証してAnalyticsだけを再起動します。health確認に失敗するとexact `git revert`でrollback commitを作り、Analyticsを再起動して復旧確認します。自動pushは行いません。

```powershell
python .\incident_automation.py approve-autofix --request-id <incident-id>
python .\incident_automation.py autofix-status --request-id <incident-id>
python .\incident_automation.py approve-autofix-merge --request-id <incident-id> --commit <40桁commit-hash>
python .\incident_automation.py approve-autofix-deploy --request-id <incident-id> --commit <40桁commit-hash>
python .\incident_automation.py cancel-autofix --request-id <incident-id> --reason "管理者判断"
```

現在の設定は[`config/codex_autofix.json`](config/codex_autofix.json)の`enabled=true` / `mode=active` / `deployment_enabled=true`です。critical障害では隔離worktreeでの修復候補作成を自動許可し、配備executorも承認済み候補を処理できます。マージ・配備・再起動・pushはそれぞれ同一commitへの別の明示承認を必要とします。Codex workerは専用標準Windowsアカウント、配備executorはAnalytics所有者の対話limited tokenへ分離します。workerタスク未登録時は候補作成を実行しません。

```powershell
python .\incident_automation.py autofix-worker --dry-run
.\scripts\register_smai_codex_autofix_worker_task.ps1 -UserId <専用Windowsユーザー> -DryRun
.\scripts\register_smai_codex_autofix_worker_task.ps1 -UserId <専用Windowsユーザー>
python .\incident_automation.py autofix-deploy-worker --dry-run
.\scripts\register_smai_codex_autofix_deploy_task.ps1 -DryRun
.\scripts\register_smai_codex_autofix_deploy_task.ps1
```

詳しい状態遷移と有効化ゲートは[`Documents/10_Codex_Autofix_Design.md`](Documents/10_Codex_Autofix_Design.md)を参照してください。

## セットアップと確認

依存関係は`setup/`に分離しています。Analytics専用環境は次で作成・更新します。

```powershell
.\setup\setup.bat
```

運用依存は`setup/requirements.txt`、確認用依存は`setup/requirements-dev.txt`です。詳細は[`setup/SETUP.md`](setup/SETUP.md)を参照してください。

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
.\venv_SMAI_Analytics\Scripts\python.exe -m py_compile analytics_web.py health.py backup.py retention.py host_maintenance.py
.\venv_SMAI_Analytics\Scripts\python.exe -m compileall -q smai_analytics
.\venv_SMAI_Analytics\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\venv_SMAI_Analytics\Scripts\python.exe health.py
.\venv_SMAI_Analytics\Scripts\python.exe backup.py create
```

## バックアップと保持

```powershell
python .\backup.py create
python .\backup.py verify <backup-path>
python .\backup.py restore <backup-path> --destination <isolated-restore-directory>
python .\backup.py smoke
python .\retention.py --dry-run
```

`backup.py`はmanifestとSHA-256を検証し、破損、欠落、未コピー、パス逸脱を復元成功として扱いません。`smoke`は隔離先へ復元するため、SMAI本体を上書きしません。Runtimeの状態・ログ・バックアップ・個人データはGit管理しません。

構成と運用の詳細は[`Documents/06_MVP_Operations_Guide.md`](Documents/06_MVP_Operations_Guide.md)、[`Documents/09_Project_Structure.md`](Documents/09_Project_Structure.md)、障害自動化は[`Documents/08_Incident_Automation_Operations.md`](Documents/08_Incident_Automation_Operations.md)を参照してください。
