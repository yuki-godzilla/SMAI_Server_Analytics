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

## 管理者通知後のCodex修復指示フロー（仕様）

この節は、現行の管理者承認を「Codexへ自動実行させる仕組み」へ拡張しないための運用仕様です。現行実装は、承認済みのローカル作業依頼を作成するところまでです。Codexの起動、コード変更、commit、push、外部送信は、どれも別途の明示操作とします。

| 状態 | 根拠となる保存物 | 実行できる主体 | 次の遷移 |
| --- | --- | --- | --- |
| `pending_investigation` | `codex_requests/<incident-id>.md`、改善レポート | 管理者 | 調査、却下、または承認 |
| `admin_notified` | Outboxの`incident`または`repeat`記録 | 管理者 | 通知内容とローカル証跡を照合する。メール受信・返信だけでは承認しない |
| `codex_approved` | `codex_approvals/<incident-id>.md`、改善レポートの承認行 | 管理者 | Codexセッションへ作業依頼を手渡す |
| `codex_acknowledged`（提案） | 改善レポートの結果行 | Codex | 再現・影響調査を開始する |
| `fix_proposed` / `verified`（提案） | 修正内容、決定的テスト、実画面確認を含む結果行 | Codex、管理者 | 管理者が結果を確認し、`resolved`または追加調査へ進める |
| `resolved` / `not_reproducible` / `out_of_scope`（提案） | 最終改善レポート | 管理者 | Incidentを閉じる。監視上のhealthy観測とは区別する |

### 通知から承認まで

1. Schedulerはcriticalを検知すると、重複を抑止したローカル下書きと改善レポートを作成し、設定済みの場合だけ固定Gmail宛先へ通知します。
2. 管理者は通知の時刻・Incident ID・severityをローカルの`codex_requests/`と改善レポートに照合します。メール本文、添付、返信、リンクのクリックを承認入力として扱いません。
3. 管理者は、原因候補・影響範囲・直近の本体操作・復旧済みかどうかを確認します。復旧済みでも原因調査が必要な場合だけ承認できます。
4. 修復調査を許可する場合だけ、管理者がサーバー上で対象IDを明示して`approve-codex`を実行します。これは再実行しても同一の承認作業依頼を返す冪等操作です。

### Codexへの手渡しと必須指示

管理者は、承認済みファイルのパスまたは内容を、**管理者が開始したCodexセッション**へ明示的に渡します。通知メールは管理者への知らせであり、Codexの起動トリガーではありません。承認済み依頼を受け取ったCodexは、少なくとも次を確認します。

1. Incident IDが承認済みファイル、下書き、改善レポートの三者で一致すること。
2. 対象がAnalyticsの責務内かを`AGENTS.md`、SMAI本体側の契約、影響範囲から確認すること。本体の投資計算、ランキング、Forecast、ユーザー体験の変更は別承認とすること。
3. criticalの根拠をhealth、audit、対象Runtimeログ、関連テストで再確認すること。再現不能なら変更せず`not_reproducible`を記録すること。
4. 修正は最小範囲とし、Runtime・secret・token・個人データをcommit、画面、外部送信へ含めないこと。
5. 変更前に対象テストと復旧判定を定め、変更後に決定的テスト、Analyticsだけの再起動、`http://localhost:8502`の実画面確認を行うこと。
6. 結果を`incident_automation.py report`で、Incident ID、状態、修正要約、検証根拠として記録すること。commit/pushは各リポジトリの`AGENTS.md`の条件を満たし、管理者の通常の承認範囲内にある場合だけ行うこと。

### 承認の有効性と中止（次の実装候補）

承認済みファイルには現在、管理者・時刻・Incident IDが残ります。運用をさらに厳格にする次段階では、`approve-codex`に24時間の有効期限、`cancel-codex`による取消、Codexが着手したことを示す`codex_acknowledged`記録を追加します。有効期限切れ、取消済み、別Incident ID、または本体側の責務へ広がる依頼では、Codexは変更を開始せず、管理者へ再承認を求めます。この提案はまだ自動実行機能ではありません。

Codexの自動起動と隔離worktreeでの自動修正は、別設計の[Codex自動起動・自動修復 設計仕様](10_Codex_Autofix_Design.md)に従います。通知・手動Codex承認とAutofix承認は同じものとして扱いません。

## 安全ガード

- `critical` 以外のヘルス状態はCodex下書きを自動生成しません。
- 同一fingerprintは30分以内に重複した下書きを発行しません。未復旧のcriticalだけは15分ごとに同じIncident IDで再通知します。
- AnalyticsはSMAIを自動修正、再起動、commit、pushしません。
- Codex作業は管理者承認済みの依頼だけで開始し、SMAI側AGENTS.mdの検証・commit・push規約に従います。
- SMTP未設定、添付不在、配送失敗は成功扱いせず、Outboxの状態に残します。
