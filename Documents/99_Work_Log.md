# Work Log

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
- `dashboard.py` のヘッダー左側へロゴ、右側の状態表示へマスコットを配置
- 画像欠損時もテキストUIで起動を継続するフォールバックを追加
