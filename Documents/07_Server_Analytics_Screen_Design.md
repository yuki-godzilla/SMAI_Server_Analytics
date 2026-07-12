# SMAI Server Analytics 画面設計

## 目的

SMAI本体の投資分析画面とは分離して、サーバーの稼働状況、ユーザー接続、処理状態、操作履歴、障害を短時間で確認できる運用コンソールを提供する。

## 画面構成

| 画面 | 初期表示 | 主な確認内容 |
|---|---|---|
| Overview | 初期タブ | healthy/degraded/critical、L1〜L3、現在セッション、処理中件数、直近障害 |
| Trends | 2番目 | L1〜L3の状態履歴、応答時間p95、SMAIデータ／Runtimeの空き容量。24時間・7日・30日を選択可能 |
| Sessions | 3番目 | ユーザーID、端末種別、開始/最終heartbeat、端末擬似ID、接続状態 |
| Activity History | 4番目 | 時刻、ユーザー、操作、対象、結果、端末、所要時間。結果フィルタ付き |
| Incidents | 5番目 | failed/error/critical、復旧、メンテナンス延期、Provider/Gateway障害 |
| Tasks | 6番目 | Autostart、Watcher、Symbol Maintenance、Analyticsの状態 |
| Logs | 7番目 | server_ops/maintenance/healthの直近ログ。通常は最後に開く |

## 視認性・妥当性

- 初期画面で障害の有無が判定できること
- 正常状態の詳細より、異常状態を上位に置くこと
- ユーザー操作履歴とrawログを同じ表へ混在させないこと
- 長いJSONやstack traceは通常表示せず、選択時の詳細に限定すること
- 状態名は`healthy`、`degraded`、`critical`、`unknown`に固定すること
- 5秒更新で、更新中の表がちらつかないこと
- 画面幅980px以上を標準とし、表は横スクロール可能にすること
- Trendsは5分単位の永続集計だけを表示し、生ログ全件を画面更新ごとに走査しないこと。未観測の時間帯は灰色の`unknown`として可視化し、正常率へ含めないこと。
- OverviewのRecovery Readinessは、最終隔離復元スモーク、最小空き容量、履歴カバレッジを並べる。復元記録や容量観測がない場合は`unknown`として表示すること。

## クライアント接続トポロジー

OverviewのService Topologyは、PCブラウザ（SMAI UI）に加えて、スマートフォンおよびタブレットからStreamlit Web Appへ接続できる構成を表示する。各クライアント種別とStreamlitの経路は、対応するセッションのheartbeatを根拠に色分けする。

- `desktop`、`smartphone`、`tablet`の3種別だけを保存・表示する。生のUser-Agent、IPアドレス、Cookieは保存・表示しない。
- heartbeatが90秒以内なら`ok`（水色の点）、90秒を超えるか明示的な切断状態なら`degraded`、明示的な通信失敗なら`critical`とする。
- 該当種別のセッションがない、端末種別が未送信、または`activity_state.json`を読めない場合は`unknown`とする。未接続を正常・失敗のどちらにも推測しない。
- `activity_state.json`のlegacy文字列セッションは引き続き読めるが、端末種別がないためトポロジー上の各クライアントは`unknown`となる。

新しいセッション記録は、次の最小契約を使う。Analyticsはこのファイルを読むだけで、SMAI本体のmoduleをimportしない。

```json
{
  "sessions": {
    "opaque-session-id": {
      "last_seen_at": "2026-07-12T00:00:00+00:00",
      "client_type": "smartphone",
      "connection_state": "connected"
    }
  }
}
```

## Analytics専用ブランド資産

Analyticsのヘッダーには、本体の世界観（深いネイビー、シアンの発光、丸みのあるSMAIロボット）を継承した専用資産を表示する。

- `assets/smai-analytics-logo.png`: 稼働状態、heartbeat、監視対象を表すシールド型ロゴ。ヘッダー左側に表示する。
- `assets/smai-analytics-wordmark.png`: シールド型ロゴと正確なアプリ名「SMAI Analytics」を一体化した横長ワードマーク。上下の余白を抑え、太く大きい文字を通常のヘッダーで主表示する。
- `assets/smai-analytics-mascot.png`: 元のSMAIロボットの体型・色・表情を維持し、薄い丸眼鏡とアナリスト用バッジを加えたAnalytics専用マスコット。背景は透過し、ヘッダー右側の状態表示に添える。
- 画像が読み込めない場合も監視画面自体は起動し、テキストタイトルと状態表示を継続する。
- ロゴ・マスコットは投資スコア、ランキング、Forecastを表現せず、運用監視の意味に限定する。
- TkinterのDPI設定に合わせてヘッダー表示時に縮小し、元画像をそのまま大きく表示しない。4KモニターではDPI倍率分の元画素を使用し、ワードマーク基準500px、マスコット基準190pxを保つ。
- WindowsのPer-Monitor DPIをTk scalingへ反映し、Pillowが利用できる場合はLANCZOSで縮小する。Pillowがない環境では2倍密度の`*-header.png`へフォールバックする。

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
- Sessionsの上段にはPC、スマートフォン、タブレット別の現在接続数と、監視開始後に確認した端末擬似IDの累計を表示する。`device_id`が未連携のセッションは累計台数として推測せず、未連携数を明示する。
- Sessionsの下段には、Analyticsが観測した初回接続、状態変化、監視対象からの消失を履歴として表示する。消失は切断を意味しないため、`unknown`として扱い「切断」と表示しない。
- Activity HistoryとIncidentsはイベントがない場合、空の表だけを表示しない。データが未連携または障害未記録である理由を表示する。
- Tasksの`unknown`は正常ではない。未登録、権限不足、タスク取得不能のいずれかとして、要確認数に含める。
- Logsは生ログだけを主表示にしない。表示行数、warning、error/failed/criticalの検出数を先に表示し、障害の一次判断を助ける。
- 地理的な地図は単一PCのlocal-first運用では優先しない。代わりにSMAI UI、Streamlit、Runtime、Analyticsの依存関係を表すservice topologyを使用する。
- Notebook表示では、DPI倍率を考慮して起動時に画面内へ自動フィットする。KPIカードは均等幅のgridで配置し、長い時刻・状態説明・パス文字列によって右端が押し出されないことを確認する。
- 大画面では情報密度を保ち、幅が狭いウィンドウまたは高DPI表示では、ヘッダーを縦配置、KPIを2段、フィルターを複数行へ自動再配置する。文字を縮小して読めなくしたり、重ねて表示したりしない。
- 狭幅ではブランドの横長画像をテキスト見出しへ切り替え、状態・最終確認時刻を先に表示する。Notebookのタブ名も短縮し、すべての画面に到達できること。
- Overviewは小さいウィンドウでもTopology、Timeline、Health Score、Check Matrixを省略しない。各パネルを1列に並べ、Overview内の縦スクロールバーで下段の診断情報まで確認できるようにする。
- Trendsも小さいウィンドウでは縦スクロール可能とし、状態履歴だけでなく応答時間と容量の下段チャートまで到達できること。
- Sessions、Activity History、Incidents、Tasksの詳細表は縦・横スクロール可能とする。Logsも長い行を切り捨てず、縦・横スクロールで調査できるようにする。
- Activity Historyは結果・ユーザー・操作で絞り込み、Incidentsは重要度で絞り込む。条件に一致しない場合は空白ではなく、再検索方法を表示する。
- activity stateが未取得・破損の場合、セッション数と処理数を0と表示せず、`—`と「不明」を表示する。
