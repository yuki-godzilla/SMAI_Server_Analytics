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

## 3. バックアップと復元

`run_backup.bat` はRuntimeの `backups/` にmanifest付きバックアップを作成します。対象はユーザーデータ、運用状態、正式な銘柄マスターです。

日付別レポート、raw HTML、ログ、再生成可能なcacheはバックアップ対象外です。バックアップ作成後はmanifestのSHA-256を検証し、月1回は別フォルダへ復元する実地確認を行います。

復元はmanifest、全ファイルのSHA-256、パスの逸脱を確認してから開始します。1件でも破損、欠落、コピー未完了（`skipped`）があれば、復元先へ書き込みません。通常の実地確認は本体を上書きせず、隔離先へ行います。

```powershell
python .\backup.py verify <backup-path>
python .\backup.py restore <backup-path> --destination <isolated-restore-directory>
```

本体データへの復元は、隔離先で内容とhashを確認した後に、対象と上書き範囲を明示して実施します。

## 4. ログ保持

通常ログは30日、障害ログは90日を基準とします。RuntimeはGit管理しません。ログにはsecret、通知topic、token、Cookie、ユーザー入力本文を記録しません。

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

現在の画面は履歴表示の基盤まで実装済みです。SMAI本体側のログイン・画面操作・主要処理からイベントを送る連携は次の実装スライスです。
