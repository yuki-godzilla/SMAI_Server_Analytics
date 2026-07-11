# SMAI Server Analytics 画面設計

## 目的

SMAI本体の投資分析画面とは分離して、サーバーの稼働状況、ユーザー接続、処理状態、操作履歴、障害を短時間で確認できる運用コンソールを提供する。

## 画面構成

| 画面 | 初期表示 | 主な確認内容 |
|---|---|---|
| Overview | 初期タブ | healthy/degraded/critical、L1〜L3、現在セッション、処理中件数、直近障害 |
| Sessions | 2番目 | ユーザーID、開始/最終heartbeat、端末擬似ID、接続状態 |
| Activity History | 3番目 | 時刻、ユーザー、操作、対象、結果、端末、所要時間。結果フィルタ付き |
| Incidents | 4番目 | failed/error/critical、復旧、メンテナンス延期、Provider/Gateway障害 |
| Tasks | 5番目 | Autostart、Watcher、Symbol Maintenance、Analyticsの状態 |
| Logs | 6番目 | server_ops/maintenance/healthの直近ログ。通常は最後に開く |

## 視認性・妥当性

- 初期画面で障害の有無が判定できること
- 正常状態の詳細より、異常状態を上位に置くこと
- ユーザー操作履歴とrawログを同じ表へ混在させないこと
- 長いJSONやstack traceは通常表示せず、選択時の詳細に限定すること
- 状態名は`healthy`、`degraded`、`critical`、`unknown`に固定すること
- 5秒更新で、更新中の表がちらつかないこと
- 画面幅980px以上を標準とし、表は横スクロール可能にすること

## Analytics専用ブランド資産

Analyticsのヘッダーには、本体の世界観（深いネイビー、シアンの発光、丸みのあるSMAIロボット）を継承した専用資産を表示する。

- `assets/smai-analytics-logo.png`: 稼働状態、heartbeat、監視対象を表すシールド型ロゴ。ヘッダー左側に表示する。
- `assets/smai-analytics-mascot.png`: ヘッドセットと運用コンソールを持つAnalytics専用マスコット。ヘッダー右側の状態表示に添える。
- 画像が読み込めない場合も監視画面自体は起動し、テキストタイトルと状態表示を継続する。
- ロゴ・マスコットは投資スコア、ランキング、Forecastを表現せず、運用監視の意味に限定する。
- TkinterのDPI設定に合わせてヘッダー表示時に縮小し、元画像をそのまま大きく表示しない。

## 監査イベント

履歴の必須項目は次のとおり。

- UTC timestamp
- user_id
- action
- target
- result
- device_id（Runtime固有saltでハッシュ化した擬似ID）
- duration_ms
- platform

token、secret、password、通知topic、入力本文、完全なIPアドレスは保存しない。

## データ欠損時の表示

- health snapshotなし：`unknown / snapshot unavailable`
- activity state破損：`unknown / state unreadable`
- 履歴なし：`No activity events recorded`
- Windowsタスク取得失敗：`unknown / task query unavailable`

空データを正常稼働と表示しない。

## UI妥当性評価スプリント（2026-07-11）

実際に起動したTkinter画面をOverview、Sessions、Activity History、Incidents、Tasks、Logsの順に確認した。以下を画面設計の受け入れ基準とする。

- 各タブの上部に、まず運用判断に使う要約カードまたは可視化を置く。詳細表・生ログは下段の調査用情報とする。
- SessionsはセッションIDの全表示やUTCの生表記を主表示にしない。IDは短縮し、heartbeatは相対時刻とローカル時刻を併記する。90秒を超えるheartbeatは`stale`として要確認に分類する。
- Activity HistoryとIncidentsはイベントがない場合、空の表だけを表示しない。データが未連携または障害未記録である理由を表示する。
- Tasksの`unknown`は正常ではない。未登録、権限不足、タスク取得不能のいずれかとして、要確認数に含める。
- Logsは生ログだけを主表示にしない。表示行数、warning、error/failed/criticalの検出数を先に表示し、障害の一次判断を助ける。
- 地理的な地図は単一PCのlocal-first運用では優先しない。代わりにSMAI UI、Streamlit、Runtime、Analyticsの依存関係を表すservice topologyを使用する。
- Notebook表示では、DPI倍率を考慮して起動時に画面内へ自動フィットする。KPIカードは均等幅のgridで配置し、長い時刻・状態説明・パス文字列によって右端が押し出されないことを確認する。
