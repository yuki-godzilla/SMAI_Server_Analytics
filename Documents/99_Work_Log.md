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
- 実画面UIレビュー第3回（セッション・改善レポート / 通常デスクトップ幅 1920px / healthy）をChromeで実施
  - 観察: ヘッダーの「接続セッション 1」と端末別の現在接続「0台」が並び、観測済みセッションと現在接続の違いが読み取りにくかった。改善レポートでは復元検証・最小空き率・履歴カバレッジと空状態の説明を一画面で確認できた。
  - 変更: ヘッダーを90秒以内の現在接続数へ変更し、観測セッション数を補足として明示した。
  - 再確認: Analyticsのみを再起動し、同じhealthy状態で「現在接続 0」「観測セッション 1件 / 90秒以内」と端末別の0台表示が一致して理解できることを確認した。
- 実画面UIレビュー第4回（概要・障害・タスク・ログ / 通常デスクトップ幅 1920px / healthyおよび隔離したcriticalテストRuntime）をChromeで実施
  - 観察: 従来のOverviewは大型のカードが連続し、現在の判断、次の確認先、サービス状態を読む視線が分かれていた。critical状態では上部KPIの状態説明に上向き矢印が表示され、障害を増加と誤読できる余地があった。
  - 変更: 小さなアプリバー、罫線で区切るKPIストリップ、状態コマンド行、3サービスの状態行、詳細タブへのインライン導線へ再構成した。KPIの状態説明は増減表示を使わない補足テキストに変更した。
  - 再確認: ChromeでhealthyのOverviewと、隔離したcritical状態のOverview・障害・タスク・ログを確認した。criticalでは「18 / 100」「重大」と赤いサービス状態・障害導線が矛盾なく表示され、カードの連続なしに障害箇所を追えることを確認した。Analyticsのみ再起動後、health endpointの`200 / ok`も確認した。
- 実画面UIレビュー第5回（概要・推移 / 狭幅390px / healthyおよび隔離したdegradedテストRuntime）をChromeで実施
  - 観察: 狭幅ではアプリバーのコンテキストを省き、状態、更新、KPI、タブを優先して縦に並べる必要があった。degradedの推移では失敗要約と検査表の先頭が、横方向のレイアウト崩れなく到達できた。
  - 変更: 第4回のレスポンシブ規則により、KPIを縦並び、状態コマンド行を一列、詳細導線を縦並びにした。追加の画面要素や書き込み操作は導入していない。
  - 再確認: ChromeでhealthyのOverview、隔離したdegradedの推移タブを実際に選択し、状態pill、`100 / 100`、`62 / 100`、失敗・重大1件の要約、検査表の先頭を確認した。
- 実画面UIレビュー第6回（ヘッダー / 通常デスクトップ幅 1920px / healthy）をChromeで実施
  - 観察: 高密度化後のヘッダーは状態を素早く読める一方、盾だけの小アイコンではAnalytics用途が伝わりにくく、以前のマスコットも表示されなくなっていた。
  - 変更: 盾と下部の大きな`SMAI Analytics`プレートを重ねた正方形アイコンを生成して左上に配置した。右上の状態pillの隣に運用マスコットを復帰し、状態判定は従来どおりpillと状態色を正とした。
  - 再確認: Analyticsのみ再起動後、Chromeで新アイコン、`SMAI Analytics`の表記、マスコット、正常状態pillを同じヘッダー内で確認した。health endpointの`200 / ok`も確認した。
- 実画面UIレビュー第7回（DashBoard / 通常デスクトップ幅 1920px / healthyおよび隔離したdegradedテストRuntime）をChromeで実施
  - 観察: 従来の概要は現在状態とサービス一覧には到達しやすい一方、端末接続、healthの変化、応答・容量・タスクの根拠を一度に把握できなかった。
  - 変更: 先頭タブを`DashBoard`へ改名し、server・PC・スマートフォン・タブレットのライブ接続トポロジー、記録済みhealthによるHealth 24H、応答p95・容量のマイクロ推移、L1〜L3・応答・容量・タスク鮮度の重要シグナルを追加した。pulseは90秒以内のheartbeatの現在性を表すだけで通信量ではない。Datadog、Amazon CloudWatch、Grafanaの公式ダッシュボード資料を参照し、概要から詳細タブへ掘り下げる構成を採用した。
  - 再確認: healthyではデスクトップの実接続1台に対応するPCへのpulseが時間差スクリーンショットで移動し、Health 24H、応答p95、最小空き率を確認した。隔離したdegradedではserver・未観測端末を要確認、L2失敗を重要シグナルとして表示し、履歴なしを正常線で補間しない空状態を確認した。Analyticsのみ再起動後、health endpointの`200 / ok`を確認した。
- 実画面UIレビュー第8回（DashBoard / 狭幅390px / 隔離したdegradedテストRuntime）をChromeで実施
  - 観察: 狭幅ではKPI、状態判断、トポロジー、履歴、根拠シグナルが横スクロールや重なりなく、縦の読み順で到達できる必要があった。
  - 再確認: Chromeの390px幅で、KPIと状態判断が縦並びになり、server・PC・スマートフォン・タブレットの各ノード、Health 24Hの履歴欠損表示、L1〜L2の重要シグナルが表示領域内に収まることを確認した。
- 実画面UIレビュー第9回（DashBoardヘッダー・ライブ接続トポロジー / 実装前確認）
  - 観察: `DashBoard`のライブ接続トポロジーは画像資産ではなく小さな文字ボックスになっていた。ヘッダーは既存の正方形アイコンとマスコットを使っているが、運用画面の識別子としては小さかった。またStreamlitのbrowser page iconは汎用の📡で、ブラウザタブ／追加アプリの識別に既存の`SMAI Analytics`アイコンを使えていなかった。
  - 変更: 既存のserver・PC・スマートフォン・タブレット画像をライブ接続トポロジーへ復帰し、文字ボックスを廃止した。ヘッダーの画像ファイルは変えずにアイコンとマスコットを拡大し、同じ既存アプリアイコンをStreamlitのpage iconへ指定した。
  - 再確認: Analyticsのみを再起動し、health endpointの`200 / ok`を確認した。Chromeの通常デスクトップ幅で、既存の正方形`SMAI Analytics`アイコンとマスコットが拡大されたヘッダー、既存画像を使うserver・PC・スマートフォン・タブレットの接続トポロジー、現在接続に対応するpulseを確認した。
- 実画面UIレビュー第10回（DashBoard Health Score / 実装前確認）
  - 観察: 状態コマンドのHealth Scoreは円形の外枠と数値だけで、以前のドーナツ型ゲージよりも値と状態色の対応が弱かった。
  - 変更: Health Scoreを現在の状態色で塗る`0〜100`のドーナツ型ゲージへ戻し、中央の数値を維持した。`unknown`は0点の灰色リングとしてfail-closedに表示する。
  - 再確認: Analyticsのみを再起動し、health endpointの`200 / ok`を確認した。Chromeの通常デスクトップ幅で、health `100`が緑のドーナツ型ゲージと中央の数値として表示されることを確認した。Streamlitが要素のインラインstyleを除去するため、状態と割合はCSSクラスで与え、ブラウザが計算した背景に`conic-gradient`が設定されることも確認した。

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
