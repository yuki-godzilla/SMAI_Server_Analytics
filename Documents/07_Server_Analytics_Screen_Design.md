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

