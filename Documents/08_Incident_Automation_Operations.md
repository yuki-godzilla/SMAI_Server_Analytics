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

登録後は、タスクの実行パス、作業ディレクトリ、実行ユーザーを確認してください。登録スクリプトはAnalytics専用仮想環境を優先し、存在しない既存環境では互換のSMAI仮想環境を明示的に選択します。OS既定の`python.exe`へは依存しません。登録自体はWindowsのlive operationなので、通常テストとは分離します。

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

## 管理者通知後の承認制Codex Autofix

手動調査用の`approve-codex`は維持しています。自動起動・隔離修復を許可するときは別の`approve-autofix`を使い、メール受信・返信・画面閲覧を承認入力にはしません。

```text
critical通知
  -> 管理者の第1承認（Incident ID）
  -> 専用workerが隔離worktreeでCodexを起動
  -> allowlist検査・決定的テスト・local commit
  -> AUTOFIX READYレポートを管理者へ通知
  -> 管理者の第2承認（40桁commit hash）
  -> cleanかつ基準HEAD一致の場合だけfast-forward
  -> AUTOFIX MERGEDレポートを通知
  -> 管理者の第3承認（同じ40桁commit hash）
  -> 利用状況・health・Git・backupのfail-closed preflight
  -> Analyticsだけを再起動してhealth・ページ到達確認
  -> 失敗時はexact git revert + Analytics再起動 + 復旧確認
  -> APPLIEDまたはROLLED BACKレポートを通知
  -> 管理者がブラウザ実画面確認・通常のpushを別途実施
```

### 第1承認・状態確認・取消

```powershell
python .\incident_automation.py approve-autofix --request-id <incident-id>
python .\incident_automation.py autofix-status --request-id <incident-id>
python .\incident_automation.py cancel-autofix --request-id <incident-id> --reason "管理者判断"
```

第1承認は24時間だけ有効です。承認時のAnalytics HEAD、試行番号、専用branchをRuntimeへ保存します。取消は冪等であり、実行中のCodexを検知したworkerは停止させます。Autofixは`analytics_web.py`、`smai_analytics/**/*.py`、`tests/**/*.py`、`Documents/**/*.md`、`README.md`だけを変更できます。

### 修復レポートと第2承認

`auto_patch_ready`通知のIncident ID、40桁commit hash、変更ファイル、差分SHA-256、検証結果を、Runtimeレポートと`autofix/<incident-id>-<attempt>` branchで照合します。差分を確認して許可する場合だけ次を実行します。

```powershell
python .\incident_automation.py approve-autofix-merge `
  --request-id <incident-id> `
  --commit <40桁commit-hash>
```

第2承認は1時間、一回限りです。targetがdirty、HEAD変更、branch／commit／parent不一致、未許可パス、期限切れのどれかを検出すると`auto_merge_blocked`で停止します。条件を直した後も同じcommitを取り込む場合は、commit hashを再確認して新しい第2承認を発行します。マージ後検証が失敗した場合は`auto_merged_validation_failed`となり、既にマージ済みであるため再起動・pushを行わず管理者が調査します。

### マージレポートと第3承認

`auto_merged_pending_deploy`通知のIncident IDとcommit hashを、Runtime状態とtarget HEADで再確認します。Analytics再起動を許可する場合だけ、同じhashを指定します。

```powershell
python .\incident_automation.py approve-autofix-deploy `
  --request-id <incident-id> `
  --commit <40桁commit-hash>
```

第3承認は30分、一回限りです。配備executorはtarget branch／HEAD／parentとclean状態、15分以内のSMAIセッション、実行中処理、10分以内のhealth snapshot、決定的テスト、新規backup manifestを確認します。一つでも不明・不一致なら`auto_deploy_blocked`となり、Analyticsを停止しません。

preflight成功後だけAnalyticsを再起動し、90秒以内に`http://127.0.0.1:8502/_stcore/health`の`ok`とページHTTP成功を確認します。成功は`auto_applied`です。再起動または確認に失敗した場合は、承認commitがcleanなHEADであることを再確認し、`git revert`でrollback commitを作ってAnalyticsを再起動します。回復は`auto_rolled_back`、revert・再起動・health確認の失敗は`auto_rollback_failed`です。reset、force、stash、自動push、SMAI本体再起動は行いません。

### Workerの準備と有効化

既定の[`config/codex_autofix.json`](../config/codex_autofix.json)は`enabled=false` / `mode=dry_run` / `deployment_enabled=false`です。まず専用Windows標準アカウントへ、Analyticsリポジトリの必要最小限のGit書き込み、Autofix Runtime、既存Incidentレポート／Outboxだけの権限と、専用Codexログインを用意します。SMAI本体のソース、ユーザーデータ、Credential Managerの不要な資格情報、管理者権限を与えません。

タスクを変更せず内容だけ確認します。

```powershell
python .\incident_automation.py autofix-worker --dry-run
.\scripts\register_smai_codex_autofix_worker_task.ps1 `
  -UserId <専用Windowsユーザー> `
  -DryRun
```

管理者が前提を確認した後だけタスクを登録します。Credentialは対話プロンプトからTask Schedulerへ渡し、ソースやRuntimeへ保存しません。

```powershell
.\scripts\register_smai_codex_autofix_worker_task.ps1 -UserId <専用Windowsユーザー>
```

登録後に実行ID、`RunLevel Limited`、作業ディレクトリ、5分間隔、`IgnoreNew`、45分上限、Codexログインを確認し、実Incidentを模したdry-runを2回行います。その後だけ設定を`enabled=true` / `mode=active`へ明示変更します。解除は次のとおりです。

```powershell
.\scripts\unregister_smai_codex_autofix_worker_task.ps1
```

配備executorはAnalyticsを起動している対話ユーザーでdry-runし、同じユーザーのInteractive・limited taskとして登録します。Codex認証情報は使いません。

```powershell
python .\incident_automation.py autofix-deploy-worker --dry-run
.\scripts\register_smai_codex_autofix_deploy_task.ps1 -DryRun
.\scripts\register_smai_codex_autofix_deploy_task.ps1
```

taskの実行ユーザー、1分間隔、`IgnoreNew`、15分上限、Analyticsだけを対象にする再起動スクリプトを確認します。成功・preflight拒否・rollback成功・rollback失敗のドリル後だけ`deployment_enabled=true`へ変更します。解除は次です。

```powershell
.\scripts\unregister_smai_codex_autofix_deploy_task.ps1
```

詳しい状態契約と禁止事項は[Codex自動起動・自動修復 設計仕様](10_Codex_Autofix_Design.md)を参照してください。

## 安全ガード

- `critical` 以外のヘルス状態はCodex下書きを自動生成しません。
- 同一fingerprintは30分以内に重複した下書きを発行しません。未復旧のcriticalだけは15分ごとに同じIncident IDで再通知します。
- AnalyticsはSMAI本体を自動修正しません。Autofixは第1承認後の隔離commit、第2承認後のfast-forward、第3承認後のAnalytics単独再起動、失敗時のexact revertだけを許可します。pushは行いません。
- Codex作業は管理者承認済みの依頼だけで開始し、Analyticsの`AGENTS.md`、allowlist、決定的検証をすべて満たさない限りマージ候補にしません。
- SMTP未設定、添付不在、配送失敗は成功扱いせず、Outboxの状態に残します。
