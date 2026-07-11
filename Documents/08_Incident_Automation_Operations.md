# 重大警告・Codex調査・改善レポート運用

## 目的

SMAI Server Analytics が L1 を含む `critical` なヘルス警告を検知したとき、SMAI本体を直接変更せずに、再現可能な調査依頼をローカル Runtime へ発行します。Codex または管理者が依頼を処理し、改善結果をレポートへ追記します。レポートは管理者メール用Outboxにも添付対象として蓄積します。

この仕組みは投資判断、ランキング、Forecast、ユーザーデータを変更しません。Analytics は SMAI private module をimportせず、HTTP health endpoint とRuntime上の安定したファイル契約だけを使います。

## 状態遷移

```text
critical health
  -> 30分重複抑制
  -> Runtime/codex_requests/<incident>.md
  -> Runtime/reports/<incident>.md (pending)
  -> Codex / 管理者が調査・修正
  -> incident_automation.py report
  -> report index + admin outbox
  -> SMTP明示設定時だけ deliver-email
```

## 保存先

`SMAI_Server_Runtime/incident_operations/` 配下に保存します。RuntimeはGit管理しません。

- `codex_requests/`: Codexまたは管理者に渡す調査依頼Markdown
- `reports/`: 改善結果を追記するMarkdown
- `codex_requests.jsonl`: 依頼の監査インデックス
- `improvement_reports.jsonl`: Analytics Reportsタブが読むレポートインデックス
- `admin_outbox/`: 管理者メール送信待ちのJSON
- `admin_notifications.jsonl`: 通知状態の監査インデックス

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

## 管理者メール

メール配送は初期状態で無効です。`SMAI_ADMIN_EMAIL_TO` が未設定ならOutboxへ `pending_configuration` として保存し、外部送信は行いません。

配送を有効にする場合だけ、OSの環境変数または既存のsecret管理で次を設定します。値をGit、Runtimeログ、レポート、UIへ記録してはいけません。

```text
SMAI_ADMIN_EMAIL_TO
SMAI_ADMIN_EMAIL_FROM
SMAI_ADMIN_SMTP_HOST
SMAI_ADMIN_SMTP_PORT=587
SMAI_ADMIN_SMTP_USERNAME       # 必要な場合のみ
SMAI_ADMIN_SMTP_PASSWORD       # 必要な場合のみ
```

設定後も配送は明示操作です。

```powershell
python .\incident_automation.py deliver-email
```

メールには対応する改善レポートMarkdownだけを添付します。秘密情報、ユーザー入力、raw provider response、LLM promptは添付・記録しません。

## 安全ガード

- `critical` 以外のヘルス状態は自動でCodex依頼にしません。
- 同一fingerprintは30分以内に重複発行しません。
- AnalyticsはSMAIを自動修正、再起動、commit、pushしません。
- Codexが修正する場合もSMAI側AGENTS.mdの検証・commit・push規約に従います。
- SMTP未設定、添付不在、配送失敗は成功扱いせず、Outboxの状態に残します。
