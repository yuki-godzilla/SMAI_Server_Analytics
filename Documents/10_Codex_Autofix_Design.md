# Codex自動起動・自動修復 設計仕様

更新日: 2026-07-15
状態: 実装前の承認済み設計。本文の自動実行機能はまだ有効化しない。
対象: `SMAI_Server_Analytics` だけ。`Smart_Market_AI`本体を変更対象に含めない。

## 1. 目的と結論

critical障害を検知し、管理者が対象Incidentを明示承認した後、Codexを非対話で起動して**隔離したGit worktree内**に最小修正と検証済みの修復commitを作成する。Codexは本番の作業ツリー、SMAI本体、Windows設定、外部サービスを変更しない。

初期版（v1）は、隔離worktreeでの「自動診断・自動修正・自動検証・修復branchへのlocal commit」までを行う。`auto_patch_ready`の結果を管理者へ通知し、管理者の**第2承認**であるマージリースが発行された場合だけ、決定的なpreflightを通して本番Analytics作業ツリーへfast-forwardマージする。Analyticsの再起動、Git push、外部公開は自動化しない。

この境界は、Codexの非対話実行で推奨される最小権限sandboxと、Analyticsのfail-closed原則に合わせる。`danger-full-access`、`--dangerously-bypass-approvals-and-sandbox`、`--dangerously-bypass-hook-trust`は使用しない。

## 2. 非目標と絶対禁止事項

- SMAI本体の投資計算、ランキング、Forecast、ユーザー体験、ユーザーデータを変更しない。
- `Smart_Market_AI`のソース、依存関係、設定、Windows Task、電源設定、Firewall、Credential Managerへ書き込まない。
- 本番のAnalytics作業ツリーへ直接書き込まない。必ずRuntime下の専用worktreeを使う。
- 隔離worktree以外での`git commit`、`git push`、pull request作成、依存関係導入、パッケージ更新、ネットワークアクセスを自動実行しない。
- SMTPの固定Gmail通知以外へ、ログ、プロンプト、パッチ、ユーザーデータ、secretを外部送信しない。
- criticalの通知、メール返信、復旧通知、画面操作だけでCodexを起動しない。
- 実行中の別Autofix、承認切れ、取消済み、証跡不整合、未許可パスを正常扱いしない。

## 3. 実行モデル

```text
critical health
  -> local incident draft + administrator notification
  -> administrator explicitly grants an "autofix" approval lease
  -> incident dispatcher validates the lease and starts one isolated worker
  -> worker creates Runtime/autofix_worktrees/<incident-id>
  -> codex exec --sandbox workspace-write in that worktree
  -> deterministic validation + policy scan
  -> one local commit on autofix/<incident-id> + Runtime report/index
  -> fixed Gmail notification: auto_patch_ready
  -> administrator reviews the report and explicitly grants a merge lease
  -> deterministic merge executor fast-forwards the local Analytics checkout
  -> Runtime report/index: auto_merged_pending_deploy or a fail-closed status
  -> administrator verifies the running service, then handles normal commit/push policy
```

Windows Task Schedulerは既存の`SMAI-Incident-Automation`を「Incident作成・通知・キュー投入」に限定する。Codex実行は別の`SMAI-Codex-Autofix-Worker`タスクが担う。Workerは5分ごとに起動を試みるが、同時実行は`IgnoreNew`、実行上限は45分とする。Codexプロセスを親プロセスから切り離さず、終了コード・JSONLイベント・結果ファイルがそろうまで次のIncidentを開始しない。

## 4. 実行前提

### 専用実行ID

Workerは日常利用者や管理者ではなく、専用の標準Windowsアカウントで動かす。実装・有効化前に、次を確認する。

- Analyticsリポジトリの読み取り、Runtimeの`incident_operations/`と`autofix_worktrees/`だけへの読み書きを許可する。
- SMAI本体はhealth・auditの必要最小限の安定契約を読み取り専用にし、ソース・ユーザーデータ・Credential Managerへのアクセスを拒否する。
- 管理者グループ、リモート共有、不要なネットワーク資格情報を持たせない。
- Codex認証情報は専用アカウントの保護されたCodexログイン状態だけを使う。`CODEX_API_KEY`を永続的な環境変数、タスクXML、ソース、ログに保存しない。

この前提を満たせない間は、Workerを登録・有効化せず、現在の管理者手渡し方式を継続する。

### Codex実行設定

Workerは次の性質を満たす固定コマンド形を使う。実際のモデル名は固定せず、専用実行IDのCodex設定で管理する。

```powershell
codex exec --ephemeral --ignore-user-config --sandbox workspace-write `
  --cd <isolated-worktree> --output-schema <result-schema.json> `
  --json <generated-autofix-prompt>
```

- `workspace-write`により書き込み先をworktreeへ限定する。
- `--ignore-user-config`により、個人のMCP、プラグイン、広い権限、意図しないhook設定を引き継がない。認証情報はCodexの保護領域からのみ読む。
- worktreeの`AGENTS.md`と生成済みの作業指示を必ず読むようPromptへ明記する。
- 終了時の最終回答はJSON Schemaで固定し、自由文だけで成功判定しない。

## 5. 承認リースと状態遷移

現在の`approve-codex`は手動調査用として維持する。Autofix用には、別コマンド`approve-autofix --request-id <id>`を導入する。

| 状態 | 意味 | 次へ進める条件 |
| --- | --- | --- |
| `pending_investigation` | critical下書き作成済み | 管理者が証跡を照合する |
| `autofix_approved` | Incident ID・承認者・承認時刻・期限・基準commitを含むリース | 期限内、取消なし、worker空き、基準commit一致 |
| `autofix_running` | 一つの隔離worktreeでCodexが実行中 | プロセス監視とrun leaseが有効 |
| `auto_patch_ready` | 許可パスだけの修復commitと必須検証が成功。管理者通知済み | 管理者が差分を確認し、第2承認または破棄を選ぶ |
| `autofix_merge_approved` | 管理者がcommit hashを指定して一回限りのマージリースを発行 | 期限内、取消なし、target HEAD・worktree・commit hashがすべて一致 |
| `auto_merged_pending_deploy` | target checkoutへfast-forwardマージ済み。再起動・push未実施 | 管理者が実画面確認、通常のcommit/push方針を実施 |
| `auto_validation_failed` | テスト、パス検査、Schema、基準commitのいずれかが失敗 | パッチを保存して停止、管理者確認 |
| `auto_merge_blocked` | targetがdirty、基準HEAD不一致、commit hash不一致、期限切れ、取消 | 自動マージなしで報告 |
| `auto_blocked` | 承認切れ、取消、並行実行、証跡不整合、権限不足 | 自動変更なしで報告 |
| `auto_failed` | Codex起動、タイムアウト、終了コード、出力解析の失敗 | 自動変更なしで報告 |
| `auto_cancelled` | 管理者が明示取消 | worker停止後に成果物を保持して終了 |
| `auto_applied`（将来） | 本番適用を別途承認して完了 | v1では遷移不可 |

Autofix承認の有効期限は24時間、実行リースは45分、マージリースは1時間とする。すべてUTCで保存する。承認・取消・開始・終了・commit hash・マージ結果は同一Incident IDに対してappend-only JSONLとMarkdownレポートへ記録する。`approve-autofix`、`approve-autofix-merge`、`cancel-autofix`、`autofix-status`は冪等にする。

## 6. worktree・入力・出力の契約

### worktree

- 配置先: `SMAI_Server_Runtime/incident_operations/autofix_worktrees/<incident-id>/`
- ブランチ名: `autofix/<incident-id>`
- 基準: 承認時に記録したAnalyticsリポジトリのHEAD commit
- 本番作業ツリーに未commit変更があっても変更しない。基準commitと作業ツリーHEADが不一致なら`auto_blocked`とする。
- worker終了後もworktree、Git diff、Codex JSONL、最終結果JSONを保持する。Retentionが期限後に削除するまでは調査証跡である。
- `auto_patch_ready`では、allowlist内だけの差分を`autofix/<incident-id>`へ一つだけlocal commitする。commit hashと差分のSHA-256は結果レポートへ記録する。remoteへのpushは禁止する。

### Codexへ渡す入力

worktree内へ、secret・生ログを除去した`AUTOFIX_WORK_ORDER.md`を生成する。内容はIncident ID、基準commit、criticalのbounded evidence、許可対象、禁止対象、検証コマンド、完了JSON Schemaだけとする。メールアドレス、認証情報、ユーザーID、Cookie、IP、生のプロンプト、raw provider responseは含めない。

### Codexが変更してよいパス

初期allowlistは次だけとする。

```text
analytics_web.py
smai_analytics/**/*.py
tests/**/*.py
Documents/**/*.md
README.md
```

次は常に拒否する。

```text
Smart_Market_AI/**
scripts/**
*.bat
*.ps1
config/**
setup/**
pyproject.toml
AGENTS.md
.git/**
**/*credential*
**/*secret*
SMAI_Server_Runtime/**
```

`AUTOFIX_WORK_ORDER.md`、結果JSON、CodexイベントJSONLはRuntimeまたはworktreeのignored領域にのみ保存し、Gitの変更対象へ含めない。

## 7. 検証と成功判定

Codexの「成功」という文章は成功条件ではない。Dispatcherが次をすべて独立に確認したときだけ`auto_patch_ready`とする。

1. Codex終了コードが0、最終結果がSchemaに適合し、Incident ID・基準commitが承認リースと一致する。
2. `git diff --check`が成功し、変更がallowlist内だけで、差分が空ではない。
3. `python -m py_compile analytics_web.py health.py backup.py retention.py`と`python -m compileall -q smai_analytics`が成功する。
4. `tests.test_analytics_web`、`tests.test_web_operations`、`tests.test_incident_automation`、`tests.ui_web_render_sprint`が成功する。
5. Codexの結果が、実行していない確認を成功と記録していない。ブラウザ実画面確認が必要な変更は`needs_operator_visual_review`として分離する。
6. Runtime、secret、token、メールアドレス、ユーザーデータ、外部URLが差分・結果・ログに含まれない。
7. branchのHEADが記録済みcommit hashと一致し、commit parentが承認時の基準commitである。

`auto_patch_ready`になった時点で、同一Incident ID、commit hash、変更ファイル一覧、検証コマンドと結果、差分SHA-256、実画面確認が未実施であることだけを記載した管理者レポートを固定Gmailへ通知する。差分本文、secret、ログ、Codexプロンプトは添付・送信しない。失敗時はworktreeを本番へ適用せず、パッチ・標準出力・安全に要約した失敗分類を保持する。自動再試行は行わない。同じIncidentの再実行は管理者による新しいAutofix承認が必要である。

## 8. 管理者の第2承認とマージ（v1）

`auto_patch_ready`は配備済みを意味しない。管理者は通知されたIncident IDとcommit hashを、Runtimeレポート・worktree・branchで照合し、差分と検証結果を確認する。許可する場合だけ、次を実行して1時間のマージリースを発行する。

```powershell
python .\incident_automation.py approve-autofix-merge `
  --request-id <incident-id> `
  --commit <autofix-commit-hash>
```

Merge executorは次をすべて確認し、どれか一つでも満たさなければ`auto_merge_blocked`として停止する。

1. マージリースが期限内で取消されていない。
2. target checkoutがcleanで、HEADがAutofix承認時の基準commitと一致する。
3. `autofix/<incident-id>`のHEADが管理者が承認したcommit hashと一致し、そのparentが基準commitである。
4. `git merge --ff-only autofix/<incident-id>`だけで取り込める。競合解決、rebase、force、stashは自動化しない。
5. マージ後に必須の決定的テストを再実行して成功する。

成功時は`auto_merged_pending_deploy`を記録し、同じ固定Gmail宛先へマージ結果を通知する。管理者は既存の`AGENTS.md`に従い、Analyticsだけを再起動し、実画面確認、通常のGit pushを別作業単位として行う。

期限切れ、取消済み、検証失敗、targetの変更、または責務外の変更を含む場合は、マージしない。パッチを破棄する場合も、原因と判断を改善レポートへ残す。

## 9. 実装順序

1. Incident状態ストアをschema v3へ拡張し、Autofix承認・期限・取消・run lease・状態照会を実装する。
2. allowlist、承認リース、基準commit、結果Schemaを検証する純粋関数と単体テストを追加する。
3. worktree作成・保持・Codexコマンド生成・allowlist commit・JSONL監査を行うworkerを実装する。最初は`--dry-run`だけを有効にする。
4. `auto_patch_ready`通知、第2承認、commit hash照合、fast-forwardだけのmerge executorを実装する。最初は`--dry-run`だけを有効にする。
5. 隔離Runtimeと偽のCodex runnerで、成功、期限切れ、取消、並行実行、未許可パス、検証失敗、target dirty、HEAD不一致、commit hash差替えを契約テストする。
6. 専用Windows実行IDとTask Scheduler設定を手動で用意し、実Codexを使うが`--dry-run`の障害対応ドリルを少なくとも2回成功させる。
7. 管理者が明示的に有効化した後だけ、実worktree修正・第2承認後のfast-forwardマージを有効にする。v1では再起動とpushを追加しない。

## 10. 将来の本番自動適用

`auto_applied`はv1の対象外である。導入を検討できるのは、少なくとも2回のdry-runと2回の`auto_patch_ready`レビューで、すべての検証・証跡・取消が機能した後とする。その時点でも、対象はAnalyticsのallowlist内で再現済みの既知障害だけとし、別の管理者承認、最新backup、現行HEAD一致、アクティブ操作なし、Analytics単独の再起動、ロールバックcommitを必須にする。

## 11. 公式資料

- [Codex 非対話モード](https://learn.chatgpt.com/docs/non-interactive-mode.md): `codex exec`、最小sandbox、JSONL、構造化出力、認証情報の扱い。
- [Codex Scheduled tasks](https://learn.chatgpt.com/docs/automations.md): unattended実行では最小権限から開始し、最初の実行結果をレビューする。
- [Codex Hooks](https://learn.chatgpt.com/docs/hooks.md): hookは信頼確認が必要であり、Autofixのためにtrust bypassを使わない。
