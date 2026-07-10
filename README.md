# SMAI Server Operations

SMAI本体とは分離した、Windows常時運用用の監視・バックアップ・障害解析リポジトリです。

## 役割

- SMAI StreamlitのL1〜L3ヘルスチェック
- Windowsデスクトップ上の運用監視画面
- ユーザーログイン、実行中処理、メンテナンス状態、直近ログの表示
- 本体のユーザーデータ・運用状態・正式な銘柄マスターのバックアップ
- ログの保持期間・容量管理

本リポジトリはSMAI本体を変更しません。`SMAI_PROJECT_ROOT`で本体パスを指定し、ログ・バックアップは`SMAI_RUNTIME_ROOT`へ保存します。

## 起動

```powershell
$env:SMAI_PROJECT_ROOT = "C:\Users\user\workspace\Smart_Market_AI"
$env:SMAI_RUNTIME_ROOT = "C:\Users\user\workspace\SMAI_Server_Runtime"
python .\dashboard.py
```

外部依存なしのTkinter画面です。SMAI本体が停止していても画面は残り、最後の状態とログを表示できます。

