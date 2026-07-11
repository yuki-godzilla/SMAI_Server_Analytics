# AGENTS.md

## Purpose

`SMAI_Server_Analytics` は、Smart Market AI（SMAI）本体を安全に常時運用するための監視・バックアップ・障害解析プロジェクトです。

本リポジトリはSMAI本体の計算、ランキング、スコア、Forecast、ユーザー画面を所有しません。SMAI本体を読み取り、運用状態を記録・表示します。

## Source of truth

1. ユーザーの明示要求
2. 本リポジトリのコードとテスト
3. SMAI本体の `AGENTS.md`、コード、テスト
4. 本リポジトリの `PROJECT_CONTEXT.md`
5. `Documents/06_MVP_Operations_Guide.md`

本体とAnalyticsの責務が異なる場合、運用の安全性を優先しつつ、勝手に本体の意味や計算結果を変更しません。

## Core principles

### Local-first

- ユーザーデータ、ログ、状態、バックアップはローカルを正とします。
- 外部GitHubへのpushは銘柄マスターの限定された成果物だけに許可します。
- secret、token、通知topic、個人データをログやcommitへ出しません。

### Deterministic and observable

- ヘルスチェックと運用判定は決定的にします。
- 状態を隠れたメモリだけに保持せず、時刻・結果・原因・対象をログへ残します。
- 不明、破損、読み取り不能は正常扱いせず、`degraded`または`critical`として表示します。

### Fail-closed

- 監視対象が不明な場合は自動再起動や自動pushを行いません。
- Git差分に許可外ファイルが含まれる場合、銘柄更新の自動commit/pushを停止します。
- バックアップ検証に失敗した場合、復元済みとは報告しません。

## Repository boundaries

- `SMAI_Server_Analytics`: 監視画面、ヘルスチェック、バックアップ、保持処理、運用文書
- `SMAI_Server_Runtime`: 実行時ログ、バックアップ、snapshot、調査用一時データ。Git管理しません
- `Smart_Market_AI`: アプリ本体、正式な銘柄マスター、deterministic domain logic

AnalyticsはSMAI本体のprivate moduleをimportしません。連携はファイル、HTTP health endpoint、プロセス、CLIの安定した契約で行います。

## Automatic commit and push

自動commit/pushの対象は以下に限定します。

- `data/marketdata/symbol_universe.csv`
- `data/marketdata/symbol_universe_sources/*.csv`
- `data/marketdata/*manifest*.json`

raw HTML、ログ、cache、temporary files、日付別レポート、ユーザーデータは自動commit/pushしません。Gitの認証情報はcredential managerまたはSSH agentを使用し、ファイルへ保存しません。

自動push前に必ず次を満たします。

- 更新処理が成功している
- lockが解放されている
- 許可対象以外の差分がない
- secret検査に問題がない
- commit対象が空でない
- push失敗を成功扱いしない

### Work-unit commit and push

- 本プロジェクトでは、完了した作業単位ごとにcommitし、検証成功後にリモートへpushすることを必須とします。複数の無関係な変更を一つのcommitへ混在させません。
- commit前に対象差分、Git status、検証結果を確認し、`git add .`を使用せず、対象ファイルを明示してstageします。
- pushは認証済みのGitHub CLI、credential manager、またはSSH agentを用い、認証情報をファイル・ログ・commitへ残しません。
- pushに失敗した場合、作業単位を公開済みとして扱いません。失敗理由を確認して再試行またはユーザーへ報告します。
- 自動pushの対象制限は上記のAutomatic commit and pushに従います。人手またはAgentによる作業単位のcommitでは、対象変更が本リポジトリの責務・安全方針・review可能性を満たすことを確認します。

## Operations UI

`dashboard.py` はTkinterの独立画面です。SMAI本体が停止していても起動を維持し、最後のhealth snapshot、ユーザー/セッション数、実行中処理、直近ログを表示します。

画面は投資判断を行いません。投資スコア、ランキング、Forecastの意味を変更・再計算しません。

### Operations UI style and autostart

- Analytics画面はSMAI本体の`ui/styles.py`に定義された、深いネイビー背景、シアン／ブルーのアクセント、カード型情報階層、緑／黄／赤の状態色を踏襲します。
- Overviewには、状態を数値化したhealth score、直近推移のtimeline、L1〜L3のcheck matrix、SMAI UI／Streamlit／Runtime／Analyticsのservice topologyを表示します。これらは運用状態の可視化であり、投資判断や本体の計算結果を表示・再計算するものではありません。
- 監視画面は異常状態を最優先で表示し、`healthy`、`degraded`、`critical`、`unknown`を正常・異常・欠損の判定に使用します。
- Windowsで常時監視する場合は、`scripts/register_smai_analytics_autostart_task.ps1`を実行し、対話ユーザーのログオン時に`run_dashboard.bat`を起動します。GUIを表示するため、Session 0のAtStartupタスクではなくInteractiveのAtLogOnタスクを使用します。
- 自動起動登録は一度に一つの`SMAI-Server-Analytics`タスクだけを作成し、二重起動を避けます。解除は`unregister_smai_analytics_autostart_task.ps1`を使用します。
- 自動起動の登録・解除はWindowsのlive operationです。通常の構文確認・単体テストとは分離し、登録後にタスクの実行パス、作業ディレクトリ、ユーザーセッション、再起動設定を確認します。

## Verification

最低限、次を確認します。

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m py_compile dashboard.py health.py backup.py retention.py
python health.py
python backup.py create
```

外部ネットワークを使う通常テストは作りません。GitHub pushはlive operationとして、通常の構文・契約確認から分離します。

## Documentation

運用方針は日本語を基本とし、MarkdownはUTF-8 without BOMで保存します。実行していない確認を実行済みと報告しません。
