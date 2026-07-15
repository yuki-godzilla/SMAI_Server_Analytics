# Codex自動起動・自動修復 設計仕様

更新日: 2026-07-16
状態: v2実装済み。既定設定は`enabled=false` / `mode=dry_run` / `deployment_enabled=false`であり、実行ID・権限・ドリルの準備と管理者による明示有効化までは自動実行しない。
対象: `SMAI_Server_Analytics` だけ。`Smart_Market_AI`本体を変更対象に含めない。

## 1. 目的と結論

critical障害を検知し、管理者が対象Incidentを明示承認した後、Codexを非対話で起動して**隔離したGit worktree内**に最小修正と検証済みの修復commitを作成する。Codexは本番の作業ツリー、SMAI本体、Windows設定、外部サービスを変更しない。

v1は、隔離worktreeでの「自動診断・自動修正・自動検証・修復branchへのlocal commit」と、第2承認後のfast-forwardマージを行う。v2はマージ結果を管理者へ通知した後、同じ40桁commit hashに対する**第3承認**が発行された場合だけ、別の配備executorが利用状況・health・Git・backupをpreflightし、Analyticsだけを再起動してhealth endpointとページ到達を確認する。配備確認に失敗した場合は`git revert`によるrollback commitを作成し、Analyticsを再起動して復旧を確認する。Git push、SMAI本体再起動、Windows再起動、外部公開は自動化しない。

この境界は、Codexの非対話実行で推奨される最小権限sandboxと、Analyticsのfail-closed原則に合わせる。`danger-full-access`、`--dangerously-bypass-approvals-and-sandbox`、`--dangerously-bypass-hook-trust`は使用しない。

## 2. 非目標と絶対禁止事項

- SMAI本体の投資計算、ランキング、Forecast、ユーザー体験、ユーザーデータを変更しない。
- `Smart_Market_AI`のソース、依存関係、設定、Windows Task、電源設定、Firewall、Credential Managerへ書き込まない。
- Codex自身は本番のAnalytics作業ツリーへ直接書き込まない。必ずRuntime下の専用worktreeを使う。
- 本番checkoutで許可する自動Git操作は、第2承認後のfast-forwardと、配備失敗時に正確な修復commitを取り消す`git revert`だけとする。`git push`、pull request作成、rebase、reset、force、stash、依存関係導入、パッケージ更新を自動実行しない。
- SMTPの固定Gmail通知以外へ、ログ、プロンプト、パッチ、ユーザーデータ、secretを外部送信しない。
- criticalの通知、メール返信、復旧通知、画面操作だけでCodexを起動しない。
- 実行中の別Autofix、承認切れ、取消済み、証跡不整合、未許可パスを正常扱いしない。

## 3. 実行モデル

```text
critical health
  -> local incident draft + administrator notification
  -> administrator explicitly grants an "autofix" approval lease
  -> incident dispatcher validates the lease and starts one isolated worker
  -> worker creates Runtime/incident_operations/autofix/worktrees/<incident-id>-<attempt>
  -> codex exec --sandbox workspace-write in that worktree
  -> deterministic validation + policy scan
  -> one local commit on autofix/<incident-id> + Runtime report/index
  -> fixed Gmail notification: auto_patch_ready
  -> administrator reviews the report and explicitly grants a merge lease
  -> deterministic merge executor fast-forwards the local Analytics checkout
  -> Runtime report/index: auto_merged_pending_deploy or a fail-closed status
  -> administrator reviews the merge report and grants a 30-minute deployment lease
  -> interactive Analytics-owner deploy executor checks sessions/operations/health/Git
  -> verified local backup -> Analytics-only restart -> health + page verification
  -> auto_applied, or exact git revert + second restart -> auto_rolled_back
  -> fixed Gmail result report; administrator performs browser visual review and normal push
```

Windows Task Schedulerは既存の`SMAI-Incident-Automation`を「Incident作成・通知・キュー投入」に限定する。Codex実行は別の`SMAI-Codex-Autofix-Worker`タスクが担う。Workerは5分ごとに起動を試みるが、同時実行は`IgnoreNew`、実行上限は45分とする。Codexプロセスを親プロセスから切り離さず、終了コード・JSONLイベント・結果ファイルがそろうまで次のIncidentを開始しない。

配備は`SMAI-Codex-Autofix-Deploy`が1分ごとに承認リースを確認し、`IgnoreNew`・15分上限で実行する。Analyticsプロセス所有者と同じ対話ユーザーのlimited tokenでのみ動かし、専用Codex実行IDへプロセス停止権限を追加しない。Codex workerと配備executorは同じRuntime lockを共有し、修復・マージ・配備を並行させない。

## 4. 実行前提

### 専用実行ID

Workerは日常利用者や管理者ではなく、専用の標準Windowsアカウントで動かす。実装・有効化前に、次を確認する。

- AnalyticsリポジトリとそのGit管理領域は、worktree作成、修復commit、第2承認後のfast-forwardに必要な範囲だけ読み書きを許可する。Runtimeは`incident_operations/autofix/`と既存のIncidentレポート／Outboxだけを読み書きできるようにする。
- SMAI本体はhealth・auditの必要最小限の安定契約を読み取り専用にし、ソース・ユーザーデータ・Credential Managerへのアクセスを拒否する。
- 管理者グループ、リモート共有、不要なネットワーク資格情報を持たせない。
- Codex認証情報は専用アカウントの保護されたCodexログイン状態だけを使う。`CODEX_API_KEY`を永続的な環境変数、タスクXML、ソース、ログに保存しない。

この前提を満たせない間は、Workerを登録・有効化せず、現在の管理者手渡し方式を継続する。

### 配備実行ID

配備executorはAnalyticsを起動している対話ユーザーの`LogonType Interactive`・`RunLevel Limited`で動かす。Codex認証情報は不要であり、Codexを起動しない。権限はAnalyticsリポジトリ、RuntimeのAutofix／backup／Incidentレポート、Analyticsプロセスの再起動に限定する。SMAI本体プロセス、Firewall、Credential Manager、Windows再起動、remote Gitへは書き込まない。

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
| `auto_merged_validation_failed` | fast-forward後の決定的検証だけが失敗 | 既にマージ済みであることを明示して通知し、再起動・pushを禁止して管理者確認 |
| `autofix_deploy_approved` | 管理者が同じcommit hashを指定した30分の第3承認 | target branch/HEAD一致、clean、利用中セッション・処理なし、fresh healthy、backup・再検証成功 |
| `autofix_deploying` | backup検証済みでAnalytics単独再起動を開始 | health endpointとページ到達を90秒以内に確認 |
| `auto_deploy_blocked` | 第3承認切れ、利用中、health不良、Git不一致、backup／事前検証失敗 | 再起動前に停止。原因を解消し、新しい第3承認 |
| `auto_applied` | 承認commitでAnalyticsが起動し、自動health・ページ確認済み | 管理者のブラウザ実画面確認後、通常のpush判断 |
| `auto_rolled_back` | 配備確認失敗後、修復commitをrevertし再起動health回復 | 管理者が原因調査。自動push禁止 |
| `auto_rollback_failed` | 配備と自動rollbackの両方が失敗 | 即時の管理者手動復旧。自動処理停止 |
| `auto_cancelled` | 管理者が明示取消 | worker停止後に成果物を保持して終了 |

Autofix承認の有効期限は24時間、実行リースは45分、マージリースは1時間、配備リースは30分とする。すべてUTCで保存する。承認・取消・開始・終了・commit hash・マージ・配備・rollback結果は同一Incident IDに対してappend-only JSONLとMarkdownレポートへ記録する。各承認、取消、状態照会は冪等にする。`autofix_deploying`開始後は取消によって再起動／rollbackを中断しない。

## 6. worktree・入力・出力の契約

### worktree

- 配置先: `SMAI_Server_Runtime/incident_operations/autofix/worktrees/<incident-id>-<attempt>/`
- ブランチ名: `autofix/<incident-id>-<attempt>`
- 基準: 承認時に記録したAnalyticsリポジトリのHEAD commit
- 本番作業ツリーに未commit変更があっても変更しない。基準commitと作業ツリーHEADが不一致なら`auto_blocked`とする。
- worker終了後もworktree、Git diff、Codex JSONL、最終結果JSONを保持する。Retentionが期限後に削除するまでは調査証跡である。
- `auto_patch_ready`では、allowlist内だけの差分を`autofix/<incident-id>-<attempt>`へ一つだけlocal commitする。commit hashと差分のSHA-256は結果レポートへ記録する。remoteへのpushは禁止する。

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
4. `tests.test_analytics_web`、`tests.test_web_operations`、`tests.test_incident_automation`、`tests.test_codex_autofix`と`tests/ui_web_render_sprint.py`が成功する。
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
3. `autofix/<incident-id>-<attempt>`のHEADが管理者が承認したcommit hashと一致し、そのparentが基準commitである。
4. `git merge --ff-only autofix/<incident-id>`だけで取り込める。競合解決、rebase、force、stashは自動化しない。
5. マージ後に必須の決定的テストを再実行して成功する。

成功時は`auto_merged_pending_deploy`を記録し、同じ固定Gmail宛先へマージ結果を通知する。v2の第3承認がない限り再起動しない。fast-forward完了後の検証だけが失敗した場合は履歴を書き換えず、`auto_merged_validation_failed`として「既にマージ済み」を明示し、配備対象にしない。

期限切れ、取消済み、検証失敗、targetの変更、または責務外の変更を含む場合は、マージしない。パッチを破棄する場合も、原因と判断を改善レポートへ残す。

## 9. 実装状態と有効化ゲート

実装済み:

1. schema v4の状態、24時間のAutofix承認、45分のrun lease、1時間のマージ承認、30分の配備承認、取消、状態照会、append-only JSONL監査。
2. allowlist、差分の機微情報検査、構造化結果Schema、隔離worktree、`codex exec`、決定的検証、単一local commit。
3. 修復準備完了・第2承認・マージ完了・停止／失敗の固定Gmail Outbox通知。
4. clean target、基準HEAD、branch HEAD、commit parent、変更パスを再検証するfast-forward限定マージ。
5. 成功、期限切れ、取消、並行worker、未許可パス、機微情報、Schema不一致、commit hash差替え、target dirty、target HEAD変更、マージ後検証失敗の契約テスト。
6. 専用標準Windowsアカウントで5分ごとに起動し、`IgnoreNew`・45分上限を設定する登録／解除スクリプト。
7. 対話中のAnalytics所有者で1分ごとに起動し、利用状況、health、branch、HEAD、backupを検証してAnalyticsだけを再起動する配備executor。
8. 再起動・health確認失敗時のexact `git revert`、2回目のAnalytics再起動、復旧／rollback失敗通知。

Live operationとして未実施:

1. 専用Windows標準アカウントの作成、ACL、Codexログイン、Windows Task登録。
2. 実Incidentを模した`--dry-run`ドリル2回と、固定Gmailへの実配送確認。
3. [`config/codex_autofix.json`](../config/codex_autofix.json)の`enabled=true` / `mode=active`への変更。
4. 配備executorのdry-run／rollbackドリル後の`deployment_enabled=true`への変更。

この3項目は実装不足ではなく、実機の認証・権限・外部送信を伴う管理者操作である。完了前は設定を有効にしない。

## 10. 管理者の第3承認と自動配備（v2）

`auto_merged_pending_deploy`通知のIncident IDとcommit hashをローカル状態・branch・target HEADで再確認し、Analytics再起動を許可する場合だけ次を実行する。

```powershell
python .\incident_automation.py approve-autofix-deploy `
  --request-id <incident-id> `
  --commit <40桁autofix-commit-hash>
```

配備executorは再起動前に、30分リース、target branch／HEAD／parent、clean checkout、15分間quietなセッション、実行中処理ゼロ、10分以内のhealthy snapshot、決定的テスト、作成直後のbackup manifestを検証する。失敗時は`auto_deploy_blocked`として再起動しない。

preflight成功後だけ`restart_analytics_web.ps1`で`analytics_web.py`プロセスを再起動する。90秒以内に`/_stcore/health`の`ok`とページHTTP成功を確認できれば`auto_applied`を記録して通知する。ブラウザでの見た目・操作確認とGit pushは管理者のまま残す。

再起動または確認に失敗した場合は、targetが承認commitのcleanなHEADであることを再確認し、`git revert --no-edit <repair-commit>`で履歴を保持したrollback commitを作る。その後Analyticsだけを再起動しhealth回復を確認する。回復時は`auto_rolled_back`、revert・再起動・healthのいずれかが失敗した場合は`auto_rollback_failed`として最優先通知し、自動push・reset・再試行を行わない。

## 11. 将来境界

自動Git push、pull request、SMAI本体再起動、Windows再起動、Firewall変更、backupからのユーザーデータ自動restoreはV2でも対象外である。追加には別仕様と明示承認が必要である。

## 12. 公式資料

- [Codex 非対話モード](https://learn.chatgpt.com/docs/non-interactive-mode.md): `codex exec`、最小sandbox、JSONL、構造化出力、認証情報の扱い。
- [Codex Scheduled tasks](https://learn.chatgpt.com/docs/automations.md): unattended実行では最小権限から開始し、最初の実行結果をレビューする。
- [Codex Hooks](https://learn.chatgpt.com/docs/hooks.md): hookは信頼確認が必要であり、Autofixのためにtrust bypassを使わない。
