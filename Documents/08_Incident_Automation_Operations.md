# 重大警告・Codex調査・改善レポート運用

## 目的

SMAI Server Analytics が L1 を含む `critical` なヘルス警告を検知したとき、SMAI本体を直接変更せずに、再現可能な調査依頼をローカル Runtime へ発行します。Codex または管理者が依頼を処理し、改善結果をレポートへ追記します。レポートは管理者メール用Outboxにも添付対象として蓄積します。

この仕組みは投資判断、ランキング、Forecast、ユーザーデータを変更しません。Analytics は SMAI private module をimportせず、HTTP health endpoint とRuntime上の安定したファイル契約だけを使います。

## 状態遷移

```text
critical health
  -> 30分重複抑制
  -> Runtime/codex_requests/<incident>.md (管理者承認待ちの下書き)
  -> Runtime/reports/<incident>.md (pending)
  -> Gmail設定済みなら管理者へ通知、未設定ならlocal outboxだけへ記録
  -> 管理者が approve-codex を明示実行
  -> Runtime/codex_approvals/<incident>.md (Codex作業依頼)
  -> Codex / 管理者が調査・修正
  -> incident_automation.py report
  -> report index + admin outbox + Gmail通知
```

## 保存先

`SMAI_Server_Runtime/incident_operations/` 配下に保存します。RuntimeはGit管理しません。

- `codex_requests/`: Codexまたは管理者に渡す調査依頼Markdown
- `reports/`: 改善結果を追記するMarkdown
- `codex_requests.jsonl`: 依頼の監査インデックス
- `improvement_reports.jsonl`: Analytics Reportsタブが読むレポートインデックス
- `admin_outbox/`: 管理者メール送信待ちのJSON
- `admin_notifications.jsonl`: 通知状態の監査インデックス
- `gmail_notification.json`: 固定Gmail宛先と再送設定。個人データを含むためGit管理しない
- `codex_approvals/`: 管理者CLIで承認されたCodex向け作業依頼

## 定期監視の開始

初回にだけ、管理者PowerShellで次を実行します。タスクはログオン中に5分ごとに `incident_automation.py once` を実行します。

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\register_incident_automation_task.ps1
```

登録後は、タスクの実行パス、作業ディレクトリ、実行ユーザーを確認してください。登録自体はWindowsのlive operationなので、通常テストとは分離します。

解除:

```powershell
.\scripts\unregister_incident_automation_task.ps1
```

手動の1回実行:

```powershell
python .\incident_automation.py once
```

## Codex調査の完了記録

調査依頼Markdownを読み、SMAI本体のhealth、audit、対象ログ、失敗テストを照合します。修正した場合は対象テストを実行し、結果を次のように記録します。

```powershell
python .\incident_automation.py report `
  --request-id <incident-id> `
  --status resolved `
  --summary "原因と実施した修正" `
  --verification "実行した確認と結果"
```

`--status` は `investigated`、`resolved`、`blocked` を基本とします。未確認事項を成功として記録しません。

## 固定Gmail通知

メール配送は初期状態で無効です。固定Gmail設定がない場合はOutboxへ`pending_configuration`として保存し、外部送信はしません。既存の明示SMTP環境変数は移行互換のためだけに残しますが、新規設定はGmailを正とします。

Gmailアカウントでは先に2段階認証を有効化し、`SMAI Analytics Alerts`用のアプリパスワードを作成します。アプリパスワードをチャット、ソース、設定ファイル、環境変数、Runtimeログへ貼り付けてはいけません。

初回設定は、対話中のWindowsユーザーで次を実行します。

```powershell
.\scripts\configure_gmail_notifications.ps1
```

このコマンドは送信元Gmailと固定通知先をRuntimeへ保存し、アプリパスワードだけをWindows Credential Managerの`SMAI-Analytics-Gmail-SMTP`へ保存します。画面・ログにはメールアドレスやパスワードを表示しません。Analytics画面は読み取り専用のまま、`設定済み`、`未設定`、`要確認`と最終配送結果だけを表示します。

設定後は、実障害と無関係な最小のテストメールを明示実行して確認します。

```powershell
.\scripts\test_gmail_notifications.ps1
```

`SMAI-Incident-Automation`タスクが5分ごとに実行されると、critical検知、15分後の未復旧再通知、healthy復帰時の復旧通知を処理します。メール本文と添付レポートはboundedな運用証跡だけであり、secret、ユーザー入力、生ログ、raw provider response、LLM promptを含めません。配送失敗は最大3回まで遅延再試行し、成功として扱いません。

件名はフローの段階を識別できるよう、初回障害は`[SMAI CRITICAL]`、未復旧再通知は`[SMAI REMINDER]`、管理者承認後のCodex依頼は`[SMAI CODEX APPROVED]`、調査結果は`[SMAI REPORT]`、healthy復帰は`[SMAI RECOVERED]`を使います。すべてに同じIncident IDとローカルレポートの添付を付けます。

配送失敗は生のSMTP応答を保存せず、`smtp_authentication`、`smtp_connection`、`smtp_protocol`の安全な分類だけを監査記録へ残します。`smtp_authentication`の場合は、送信元Gmailの2段階認証、アプリパスワード、送信元アドレスの組み合わせを見直してください。

状態だけを確認する場合は次を使います。

```powershell
python .\incident_automation.py notification-status
```

## Codex作業依頼の管理者承認

critical検知時点では`codex_requests/`へ下書きだけを保存し、Codexの修正作業は開始しません。管理者が内容を確認した後、次を明示実行します。

```powershell
python .\incident_automation.py approve-codex --request-id <incident-id>
```

承認済み依頼は`codex_approvals/`へ別ファイルとして保存されます。依頼には影響調査、決定的テスト、`http://localhost:8502`の実画面確認、管理者への修正報告を必須として記載します。メール返信やAnalytics画面の操作を承認として解釈しません。

## 安全ガード

- `critical` 以外のヘルス状態はCodex下書きを自動生成しません。
- 同一fingerprintは30分以内に重複した下書きを発行しません。未復旧のcriticalだけは15分ごとに同じIncident IDで再通知します。
- AnalyticsはSMAIを自動修正、再起動、commit、pushしません。
- Codex作業は管理者承認済みの依頼だけで開始し、SMAI側AGENTS.mdの検証・commit・push規約に従います。
- SMTP未設定、添付不在、配送失敗は成功扱いせず、Outboxの状態に残します。
