# SMAI Server Analytics - Project Context

## 目的

SMAI本体を安全に常時運用するための監視、バックアップ、保持、障害解析を提供する。AnalyticsはSMAI本体の計算、ランキング、Forecast、ユーザー画面を所有せず、ファイル、HTTP health endpoint、プロセス、CLIの安定した契約だけを読み取る。

## 正規の画面と起動

正規の運用画面は`analytics_web.py`（実装は`smai_analytics/ui/web_dashboard.py`）による読み取り専用のStreamlit Web Operations Consoleである。通常は`run_analytics_web.bat`で起動し、MagicDNS URLの`http://smai-server:8502`からPC、タブレット、スマートフォンへ提供する。Main Applicationは同じホスト名の`http://smai-server:8501`であり、Analyticsとはポートで分離する。サーバーPC内の確認だけは`http://localhost:8502`を使用する。URL設定は`config/network.json`に集約し、`0.0.0.0`は待受専用で画面・起動案内には表示しない。自動起動は`SMAI-Server-Analytics`のInteractive AtLogOnタスク、再起動は`restart_analytics_web.bat`を使用する。

## 現在の優先順位

モバイル／タブレットのresponsive改善スプリントを完了した後の次段階は、(1) 自動起動・定期監視の実運用確認、(2) 月次復元スモークテストの定着、(3) 障害対応ドリル、(4) 狭幅を含む受け入れテストである。障害対応ドリルではcritical検知からローカル調査依頼、固定Gmailへの管理者通知、管理者承認済みのCodex修正依頼、改善レポート表示までを追跡する。Gmailの送信先はRuntimeの固定設定、アプリパスワードはWindows Credential Managerだけに保存し、画面・Git・ログへメールアドレスやsecretを出さない。Codexへの修正依頼は承認済みの作業指示を作成するまでとし、自動でコード変更や外部送信を開始しない。SMAI本体の計算、ランキング、Forecast、ユーザーデータは変更しない。

## データ境界

- `SMAI_Server_Analytics`: versionedな監視・運用コード、設定、文書
- `SMAI_Server_Runtime`: logs、backups、snapshots、調査用一時データ。Git管理しない
- `Smart_Market_AI`: SMAI本体と正式な銘柄マスター

不明、破損、読み取り不能を正常扱いしない。Runtime、secret、token、Cookie、個人データをcommitしない。TCP 8502をインターネットへ公開しない。
