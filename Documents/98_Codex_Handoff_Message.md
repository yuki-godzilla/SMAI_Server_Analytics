# SMAI Server Analytics 引継ぎ・実画面UI改善指示書

更新日: 2026-07-13
対象リポジトリ: `C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Analytics`
作業ブランチ: `agent/analytics-operations-console`
最新commit: `a5c969a refactor: focus analytics overview on next actions`（`origin`へpush済み）

## 1. 次セッションで最初に行うこと

1. この文書、`AGENTS.md`、`PROJECT_CONTEXT.md`、`Documents/07_Server_Analytics_Screen_Design.md`、`Documents/99_Work_Log.md`を読む。
2. `git status --short --branch`で、引継ぎ時点の作業ツリーがクリーンであることを確認する。
3. `http://localhost:8502/_stcore/health`を確認する。引継ぎ時点ではTCP 8502で待受中、health endpointは`200 / ok`だった。
4. Browser操作スキルを使い、`http://localhost:8502`の実画面へ接続する。前セッションではBrowser runtimeが`No browser is available`を返したため、通常のユーザーブラウザが自動共有されるとは仮定しない。新セッションでは必ず再接続を試す。

Browser接続が利用できない場合は、画面を見たと偽らない。ユーザーへ、更新後の画面スクリーンショットをチャットに添付してもらい、その画像を実画面の根拠として反復する。

## 2. ユーザーの明示要求（未完了）

Streamlit Web Operations Consoleについて、実画面を確認しながらUI/UX、視覚的な分かりやすさ、情報密度、情報の理解しやすさを改善する。**変更 → 実画面確認 → 評価 → 改善**をおよそ5回繰り返すこと。

特に、情報を一ページへ集め過ぎず、タブ切替で適度に分散させること。Analyticsは読み取り専用の運用画面であり、SMAI本体の計算、ランキング、Forecast、投資判断を変更・再計算してはならない。

## 3. 現在の画面設計と実装済みの第1変更

正規画面は`analytics_web.py`、実装は`smai_analytics/ui/web_dashboard.py`、起動は`run_analytics_web.bat`である。8タブは次のとおり。

| タブ | 現在の責務 |
| --- | --- |
| 概要 | health score、現在状態、Next Check、SMAI UI / Runtime / Analyticsの現在値、詳細タブへの導線 |
| 推移 | 最新L1〜L3 Check Matrix、health、応答時間、容量、タスク鮮度の時系列 |
| セッション | 端末種別ごとの現在接続、セッション一覧、観測履歴 |
| 操作履歴 | 期間・結果・ユーザー・操作名で絞る監査履歴 |
| 障害 | failed / error / criticalの記録 |
| 改善レポート | Recovery Readiness（復元検証、最小空き率、履歴カバレッジ）と調査結果 |
| タスク | Scheduled Taskの鮮度、実行結果、失敗理由 |
| ログ | 直近の運用ログ |

`a5c969a`で行った第1変更:

- OverviewからHealth Timeline、詳細なL1〜L3 Check Matrix、Recovery Readiness、端末別の6カードTopologyを外した。
- 上記の詳細を、推移・改善レポート・セッションへ分散した。
- Overviewには`NEXT CHECK`を追加した。overallが`critical`なら障害、`degraded`または`unknown`なら推移、Task鮮度に要確認があればタスクを案内する。欠損Taskを失敗扱いしないテストも追加した。
- `Documents/07_Server_Analytics_Screen_Design.md`と`Documents/99_Work_Log.md`を新しい分散方針に更新した。

これはコード・レンダラー検証済みだが、**変更後の実画面を根拠にした視覚レビューはまだ0回**である。ユーザーが最初に共有した画像は変更前の画面であり、今回の5回には数えない。

## 4. 実画面レビューの進め方（5回）

各回で必ず、対象画面・表示幅・状態・観察事項・変更内容・再確認結果を`Documents/99_Work_Log.md`へ追記する。実行していない確認を実行済みとは記録しない。

1. **Overview / 通常デスクトップ幅 / healthy**
   - 最初の3秒で健康状態と次の確認先が理解できるか。
   - ヘッダー、KPI、gauge、3サービス、導線の縦密度と余白を確認する。
2. **推移 / 通常デスクトップ幅 / degraded**
   - 最新Check Matrix、期間選択、health history、latency、storageの読み順とグラフ軸を確認する。
   - 障害時に黄色・赤・unknownが埋もれないかを確認する。
3. **セッション・改善レポート / 通常デスクトップ幅 / healthyまたは高件数**
   - 接続端末、復元準備、表の列数、説明文、空状態を確認する。
4. **障害・タスク・ログ / 通常デスクトップ幅 / critical**
   - 重大状態、失敗理由、時刻、表の横スクロール、ログの根拠が追えるかを確認する。
5. **概要・推移 / 狭幅（スマートフォンまたは狭いウィンドウ） / healthyとdegraded**
   - タブ到達性、縦並び、文字の縮小、操作部の詰まり、横スクロールを確認する。

改善は一度に無関係な変更を混ぜない。各回は、対象の実画面を確認した後に最小の修正を加え、`restart_analytics_web.bat`でAnalyticsだけを再起動し、同じ条件で再確認する。

## 5. 起動・再起動・確認コマンド

```powershell
cd C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Analytics
.\run_analytics_web.bat

# Analyticsだけを再起動（SMAI本体のStreamlitは停止しない）
.\restart_analytics_web.bat

# 本PCの画面を開く
Start-Process "http://localhost:8502"

# health確認
Invoke-WebRequest http://localhost:8502/_stcore/health -UseBasicParsing
```

`run_analytics_web.bat`はAnalytics専用venvがなければ、本体側`venv_SMAI`を互換環境として使用する。前セッションでは`venv_SMAI_Analytics`は存在しなかったが、`C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI\venv_SMAI\Scripts\python.exe`は利用できた。

## 6. 実行済みの検証

以下は`a5c969a`作成前に実行し、成功している。

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
..\Smart_Market_AI\venv_SMAI\Scripts\python.exe -m py_compile analytics_web.py health.py backup.py retention.py
..\Smart_Market_AI\venv_SMAI\Scripts\python.exe -m compileall -q smai_analytics
..\Smart_Market_AI\venv_SMAI\Scripts\python.exe -m unittest tests.test_analytics_web tests.test_web_operations -v
..\Smart_Market_AI\venv_SMAI\Scripts\python.exe tests\ui_web_render_sprint.py
```

結果:

- 単体・契約テスト: 11件成功
- Streamlit renderer: `healthy`、`degraded`、`critical`、高件数、復旧後の5状態すべて成功
- `git diff --check`: 成功
- `http://127.0.0.1:8502/_stcore/health`: `200 / ok`

この5状態レンダラー確認は視覚的な実画面レビューの代替ではない。実画面の5回反復は未完了である。

## 7. 安全・Gitの必須事項

- `AGENTS.md`を最優先する。Analyticsは本体のprivate moduleをimportせず、安定したファイル・HTTP・プロセス・CLI契約を読むだけにする。
- Runtime、ログ、バックアップ、ユーザーデータ、secret、token、CookieをGitへ追加しない。
- 変更した作業単位ごとに、対象差分、`git status`、検証結果を確認してからcommitする。`git add .`は禁止で、対象ファイルを明示する。
- 検証成功後、`origin/agent/analytics-operations-console`へpushする。push失敗を成功扱いしない。
- Windowsのlive operation（自動起動タスク登録など）は、今回のUI改善とは分離し、明示要求がない限り実行しない。
