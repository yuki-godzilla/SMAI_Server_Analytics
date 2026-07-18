# SMAI Server Analytics セットアップ

この手順はWindowsとPowerShellを前提にしています。Analyticsは本体SMAIとは別リポジトリのため、仮想環境も`venv_SMAI_Analytics`として分離します。本体の`venv_SMAI`へ依存関係を追加する必要はありません。

## かんたんセットアップ

リポジトリ直下で実行します。

```powershell
.\setup\setup.bat
```

Python 3.11または3.12を検出し、次を実行します。

- `venv_SMAI_Analytics/` を作成、または既存環境を再利用
- `setup/requirements.txt` の運用依存を導入
- `setup/requirements-dev.txt` の確認用依存を導入
- Pillow、Streamlit、pytest、ruffの利用可否を確認

既存の仮想環境は削除しません。依存関係を最初から構築したい場合は、`venv_SMAI_Analytics/`を内容確認後に手動で削除してから再実行してください。

## 依存関係の役割

| ファイル | 対象 | 内容 |
| --- | --- | --- |
| `setup/requirements.txt` | 運用時 | ブランド画像表示用Pillow、Web Operations Console用Streamlit |
| `setup/requirements-dev.txt` | 開発・確認時 | pytest、ruff、black |

## 起動

```powershell
# 信頼済みLANから閲覧できるWeb運用画面（TCP 8502）
.\run_analytics_web.bat
```

Web画面の起動スクリプトは、まず`venv_SMAI_Analytics`を使います。既存環境との互換性のため、本体側の`venv_SMAI`がある場合だけフォールバックします。TCP 8502をインターネットへ公開しません。

## 確認

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
.\venv_SMAI_Analytics\Scripts\python.exe -m py_compile analytics_web.py health.py backup.py retention.py
.\venv_SMAI_Analytics\Scripts\python.exe -m compileall -q smai_analytics
.\venv_SMAI_Analytics\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\venv_SMAI_Analytics\Scripts\python.exe health.py
.\venv_SMAI_Analytics\Scripts\python.exe backup.py create
```

通常の確認で外部ネットワークを必要とするテストは実行しません。LAN公開やWindows Firewallの変更はlive operationとして、通常の構文・テスト確認とは分離します。
