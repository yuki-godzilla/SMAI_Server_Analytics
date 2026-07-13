# Work Log

## 2026-07-14

- 実画面UIレビュー第1回（概要 / 通常デスクトップ幅 1920px / healthy）をChromeで実施
  - 観察: health score、現在状態、Next Checkの導線は最初の画面で確認できた。一方、状態表示と説明見出しに英日混在があり、運用判断の読み順が分散していた。
  - 変更: OverviewのKPI、健全性カード、確認導線、サービス概要とサービス説明を日本語の運用語へ統一した。
  - 再確認: Analyticsのみを再起動し、health endpointの`200 / ok`と同一幅のOverviewで、ヘルススコア、現在の実行状態、次に確認、サービス概要の表示を確認した。
- 実画面UIレビュー第2回（推移 / 通常デスクトップ幅 1920px / 隔離したdegradedテストRuntime）をChromeで実施
  - 観察: L2の失敗はCheck Matrixの白文字だけで、黄色の全体状態に埋もれていた。履歴が未収集であることは明示され、正常扱いされていなかった。
  - 変更: 最新Check Matrixの直前に、失敗・重大、要確認・期限超過、不明の件数をfail-closedで要約する状態色付きアラートを追加した。
  - 再確認: 隔離環境の同一degraded状態で、失敗・重大 1件が赤いアラートとして表の直前に表示され、対象行を追えることを確認した。通常のAnalyticsも再起動後にhealth endpointの`200 / ok`を確認した。

## 2026-07-13

- Overviewを「現在の安全性と次の確認先」に絞り、時系列・検査表・復元準備・端末別詳細を推移、改善レポート、セッションへ分散
- overall状態とTask鮮度に応じて、確認すべきタブを決定的に案内するNext Checkを追加
- healthy、degraded、critical、高件数、復旧後の5状態をStreamlitレンダラーで再確認
- Tkinter版を廃止し、`analytics_web.py`を正規のWeb Operations Console入口へ統一
- Overview、推移、セッション、操作履歴、障害、改善レポート、タスク、ログの8画面をWeb版へ実装
- 共有されたChrome全画面を確認し、4K／通常モニター向けにコンテンツ幅、カード内の画像配置、文字・余白、timelineのラベル密度を改善
- healthy、degraded、critical、高負荷、復旧後の5状態をStreamlitの実レンダラーで検証
- `run_analytics_web.bat`、`restart_analytics_web.bat`、Interactive AtLogOn自動起動タスクをWeb版へ統一し、TCP 8502の起動・health・HTML配信・タスク設定を確認
- Tkinter実装、旧ランチャー、旧再起動スクリプト、旧UIテストを削除

## 2026-07-12

- `telemetry.py` を追加し、health snapshotを日別の生記録と5分集計へ分離して永続化
- Streamlit health/page、TCP、L3保存チェックの所要時間と、SMAIデータ／Runtimeの容量ヘッドルームをhealth snapshotへ追加
- OverviewへRecovery Readiness、`推移`画面へL1〜L3状態履歴、応答時間p95、容量推移を追加
- 24時間・7日・30日の推移表示で、観測欠損を`unknown`として可視化し、正常率に含めないようにした
- Tkinter実画面の全8タブを対象に、標準・ノートPC相当・狭幅の3回のUI妥当性検証スプリントを実施
- 第1回で高DPI時のブランド領域過大を確認し、狭幅ではテキスト見出しと状態・最終確認時刻を優先する表示へ改善
- 第2回で狭幅のタブ到達性と推移下段の到達性を確認し、短縮タブ名と推移ページの縦スクロールを追加
- 第3回で全画面と推移下段の到達性を再確認
- Windows Task Schedulerの最終実行、次回予定、最終結果、実行パスをRuntimeへ5分ごとまたは状態変化時に記録する`task_monitor.py`を追加
- Tasksへ鮮度・最終実行・次回予定・判定理由を追加し、TrendsへJOB FRESHNESSを追加

## 2026-07-11

- SMAI本体と運用監視を分離するため、`SMAI_Server_Analytics` リポジトリを作成
- GitHub `yuki-godzilla/SMAI_Server_Analytics` のmainへ初期push
- Tkinter監視画面、L1〜L3ヘルスチェック、Runtimeログ方針を追加
- 本体の銘柄更新成果物は正式マスターとmanifestのみ自動commit/pushする方針を採用
- raw、cache、日付別レポートは生成物としてRuntimeまたはignored領域に置く方針を採用
- 実画面を用いたUI妥当性評価を実施し、Overviewのservice topology、health gauge、timeline、check matrixを確認
- Sessions、Activity History、Incidents、Tasks、Logsを「要約と可視化を上段、詳細を下段」の構成へ改善
- セッションID短縮、heartbeat相対時刻、空状態の説明、Windows Taskのunknown表示、ログ重要語集計を追加
- SMAI本体のマスコット画像を参照し、Analytics専用の運用監視マスコットを生成
- heartbeat、health、status bar、shieldをモチーフにしたAnalytics専用ロゴを生成
- シールドと「SMAI Analytics」のアプリ名を一体化した横長ワードマークを追加
- `dashboard.py` のヘッダー左側へロゴ、右側の状態表示へマスコットを配置
- 画像欠損時もテキストUIで起動を継続するフォールバックを追加
- TkinterのWindows DPI scalingを明示し、PillowのLANCZOS縮小と2倍密度ヘッダー画像のフォールバックを追加
- 全TreeviewとLogsへ縦・横スクロールバーを追加
- Activity Historyの結果・ユーザー・操作フィルター、Incidentsの重要度フィルター、該当なし表示を追加
- activity state欠損時にセッション数・処理数を正常な0と誤表示しないよう改善
- 4Kヘッダー向けにワードマーク上下余白をトリミングし、太字・大サイズ表示へ更新
- 元のSMAIマスコットの世界観を維持した眼鏡付きアナリスト版へ差し替え、背景を透過PNG化
- 4K／高DPI時はUI scaling倍率に応じて元画像から読み込み、低DPI時は2倍密度画像へフォールバックする表示経路を追加
