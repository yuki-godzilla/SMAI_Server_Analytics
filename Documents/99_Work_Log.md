# Work Log

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
