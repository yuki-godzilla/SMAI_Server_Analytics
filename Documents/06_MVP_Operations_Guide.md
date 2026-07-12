# SMAI Server Analytics 運用ガイド

## 1. 運用モデル

SMAI本体、Analytics画面、Runtimeデータを分離します。SMAI本体は `Smart_Market_AI`、監視画面と診断コードは `SMAI_Server_Analytics`、ログとバックアップは `SMAI_Server_Runtime` に置きます。

画面はPC上で `run_dashboard.bat` を起動します。SMAIが停止しても、最後に取得した状態と直近ログを確認できます。

## 2. ヘルスチェック

`run_health.bat` は次を記録します。

- L1: TCP 8501、Streamlit `/_stcore/health`
- L2: Streamlitトップページ応答
- L3: `data/ops/server_ops` と `data/user` の読み書き

L1失敗は `critical`、L2/L3のみの失敗は `degraded`、全成功は `healthy` です。snapshotは本体の `data/ops/server_ops/health_snapshot.json`、履歴はRuntimeのhealth logへ保存します。

### 推移・容量・復旧可能性

`推移`画面は、5分単位に集計したL1〜L3の状態履歴、Streamlit health/page応答のp95、SMAIデータとRuntimeの空き容量を表示します。画面を再起動しても履歴は失われません。過去24時間、7日、30日を選択でき、観測が欠けた時間帯は正常率へ加えず灰色の`unknown`として表示します。

healthの生記録は `Runtime/logs/health/YYYY-MM-DD.jsonl` に日別保存し、調査用に2日間保持します。画面用の5分集計は `Runtime/metrics/health/YYYY-MM-DD.jsonl` に30日間保持します。Retentionは両方を期限に従って削除します。

Overviewの`Recovery Readiness`は、`backup.py smoke` が記録した最終隔離復元検証、最小空き容量、選択中期間の履歴カバレッジを示します。記録がない・読めない場合は成功と推測せず`unknown`として扱います。

### クライアント通信の確認

OverviewのService Topologyでは、PCブラウザ、スマートフォン、タブレットとStreamlitの各経路を確認できます。これは端末に対する外向きpingではなく、SMAIが受信したセッションheartbeatの鮮度を確認する仕組みです。90秒以内のheartbeatを`ok`、90秒超過または明示的な切断を`degraded`、明示的な失敗を`critical`として表示します。

端末種別ごとの通信証跡がない場合、端末種別が未送信の場合、または`activity_state.json`を読み取れない場合は`unknown`です。利用者がいないことを障害と推測せず、証跡がないことを正常とも扱いません。保存対象は`desktop`、`smartphone`、`tablet`の種別と最終通信・接続状態だけであり、生のUser-Agent、IPアドレス、Cookieは記録しません。

### 接続数・接続履歴

Sessions画面の上段では、PC、スマートフォン、タブレットごとに、90秒以内のheartbeatを根拠にした現在接続数を表示します。累計はAnalyticsが監視を開始してから確認した`device_id`（Runtime固有saltによる擬似ID）だけを数えます。`device_id`が未連携のセッションは推測で台数へ加えず、`ID未連携`として表示します。

接続観測の履歴はRuntimeの`connections/watch_state.json`に保存します。初回観測、状態変化、監視対象からの消失を記録しますが、セッションがファイルから消えたことを切断と断定しません。状態ファイルが破損・読み取り不能の場合は履歴と累計を`unknown`として扱い、空の正常値に置き換えません。

## 3. バックアップと復元

`run_backup.bat` はRuntimeの `backups/` にmanifest付きバックアップを作成します。対象はユーザーデータ、運用状態、正式な銘柄マスターです。

日付別レポート、raw HTML、ログ、再生成可能なcacheはバックアップ対象外です。バックアップ作成後はmanifestのSHA-256を検証し、月1回は別フォルダへ復元する実地確認を行います。

復元はmanifest、全ファイルのSHA-256、パスの逸脱を確認してから開始します。1件でも破損、欠落、コピー未完了（`skipped`）があれば、復元先へ書き込みません。通常の実地確認は本体を上書きせず、隔離先へ行います。

```powershell
python .\backup.py verify <backup-path>
python .\backup.py restore <backup-path> --destination <isolated-restore-directory>

# 作成・検証・隔離先復元・復元物のhash照合を一度に行う
python .\backup.py smoke
```

本体データへの復元は、隔離先で内容とhashを確認した後に、対象と上書き範囲を明示して実施します。

`smoke` は本体データを上書きしません。Runtime配下の一時ディレクトリへ復元して削除し、結果を `backup_restore_smoke.json` と `logs/backup_restore_smoke.log` に記録します。バックアップ作成、manifest検証、復元、復元物のhash照合、結果記録のいずれかが失敗した場合は `critical` として終了します。

## 4. ログ保持

通常ログと5分集計は30日、health生記録は2日、障害ログは90日を基準とします。RuntimeはGit管理しません。ログにはsecret、通知topic、token、Cookie、ユーザー入力本文を記録しません。

## 5. 銘柄更新とGit

銘柄更新成功後に限り、本体側の限定された成果物をcommit/pushします。

- 追跡: `symbol_universe.csv`、source CSV、manifest JSON
- 非追跡: raw取得物、実行ログ、cache、日付別レポート、ユーザーデータ

許可外の差分がある場合はfail-closedで自動pushを停止します。

## 6. 障害対応

1. Analytics画面のoverallと最終確認時刻を見る
2. L1/L2/L3のどの層が失敗したかを確認する
3. `SMAI_Server_Runtime/logs` と本体のserver_opsログを確認する
4. 実行中処理・session・lockを確認する
5. 処理中でなければ段階停止を実行する
6. 復旧後にhealthとバックアップ検証を再実行する

## 7. 操作履歴と端末情報

AnalyticsのActivity Historyは、Runtimeの`audit/events.jsonl`を読み取ります。イベントにはUTC時刻、ユーザーID、操作名、対象、結果、所要時間、端末擬似ID、OSが含まれます。

端末擬似IDはRuntime固有のsaltと端末情報から生成し、IPアドレスを識別子にしません。token、secret、password、通知topic、入力本文はイベントへ保存しません。イベントログ自体はユーザー情報を含むため、RuntimeをGitへcommitせず、保持期限とバックアップ対象を明示して管理します。

SMAI本体は、次の操作を同じJSONL契約でRuntimeへ記録します。

- プロフィール開始・セッション解除・ユーザー切替
- 画面遷移（同一画面のStreamlit再実行は記録しない）
- コックピットの市場データ取得
- ランキング作成
- Copilotから実行するデータ取得・AI調査・レポート作成などの確認済み操作

記録処理はbest-effortです。Runtimeへの書き込みに失敗しても本体の利用操作を失敗扱いにせず、失敗は本体ログで追跡します。イベントmetadataにはtoken、secret、password、通知topic、入力本文を保存しません。
