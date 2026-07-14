# SMAI Server Analytics - Project Context

## 目的

SMAI本体を安全に常時運用するための監視、バックアップ、保持、障害解析を提供する。AnalyticsはSMAI本体の計算、ランキング、Forecast、ユーザー画面を所有せず、ファイル、HTTP health endpoint、プロセス、CLIの安定した契約だけを読み取る。

## 正規の画面と起動

正規の運用画面は`analytics_web.py`（実装は`smai_analytics/ui/web_dashboard.py`）による読み取り専用のStreamlit Web Operations Consoleである。通常は`run_analytics_web.bat`で起動し、信頼済みプライベートLANのTCP 8502からPC、タブレット、スマートフォンへ提供する。自動起動は`SMAI-Server-Analytics`のInteractive AtLogOnタスク、再起動は`restart_analytics_web.bat`を使用する。

## 現在の優先順位

次の運用開始準備（自動起動・復元スモーク・障害対応ドリル）へ進む前に、SMAI本体と同じviewport契約を使うモバイル／タブレットのresponsive改善スプリントを完了する。対象はiPhone相当の375px、iPad縦810px、iPad横1080px、PC 1366px以上であり、表示だけを改善する。表はスマホで項目名付きの証跡カード、推移は暗色チャートと間引いた時刻軸を使い、Appleホーム画面追加には専用アイコンを使う。SMAI本体の計算、ランキング、Forecast、ユーザーデータは変更しない。

## データ境界

- `SMAI_Server_Analytics`: versionedな監視・運用コード、設定、文書
- `SMAI_Server_Runtime`: logs、backups、snapshots、調査用一時データ。Git管理しない
- `Smart_Market_AI`: SMAI本体と正式な銘柄マスター

不明、破損、読み取り不能を正常扱いしない。Runtime、secret、token、Cookie、個人データをcommitしない。TCP 8502をインターネットへ公開しない。
