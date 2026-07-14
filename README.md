# SMAI Server Analytics

SMAI本体を安全に常時運用するための、ローカルファーストな監視・バックアップ・障害解析プロジェクトです。正規の画面は、PC・タブレット・スマートフォンから同じ状態を確認できる読み取り専用のWeb Operations Consoleです。本リポジトリはSMAI本体の投資計算、ランキング、Forecast、ユーザー画面を所有しません。

## Web Operations Console

セットアップ後、次のランチャーで起動します。

```powershell
.\run_analytics_web.bat
```

SMAI本体のTCP 8501とは別のTCP 8502で待ち受け、ローカルURLと検出したLAN URLを表示します。同じ信頼済みプライベートネットワーク上の端末で、たとえば`http://192.168.x.x:8502`を開いてください。

- Overview、推移、セッション、操作履歴、障害、改善レポート、タスク、ログを5秒ごとに更新します。
- Overviewにはhealth score、サービス構成、health timeline、L1〜L3 check matrix、Recovery Readinessを表示します。
- 異常、欠損、読み取り不能は正常扱いにせず、`degraded`、`critical`、`unknown`として表示します。
- SMAIの計算、ランキング、Forecast、ユーザーデータ、タスク設定を変更しません。
- TCP 8502をインターネットへ公開しません。接続できない場合だけ、Windows Firewallの**プライベート**プロファイルでTCP 8502の受信許可を確認してください。

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

## セットアップと確認

依存関係は`setup/`に分離しています。Analytics専用環境は次で作成・更新します。

```powershell
.\setup\setup.bat
```

運用依存は`setup/requirements.txt`、確認用依存は`setup/requirements-dev.txt`です。詳細は[`setup/SETUP.md`](setup/SETUP.md)を参照してください。

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
.\venv_SMAI_Analytics\Scripts\python.exe -m py_compile analytics_web.py health.py backup.py retention.py
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
