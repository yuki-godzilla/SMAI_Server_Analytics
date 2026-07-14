# SMAI Server Analytics プロジェクト構成

## 方針

実装コードは`SMAI_Server_Analytics`の責務ごとに`smai_analytics/`へ置きます。一方で、Windowsタスク、バッチ、運用手順が参照するルートの`analytics_web.py`、`health.py`などは互換入口として残します。互換入口は実装を持たず、対応するpackage moduleを起動または公開します。

```text
SMAI_Server_Analytics/
├─ smai_analytics/             # 実装本体
│  ├─ monitoring/              # health / telemetry / session / task observations
│  ├─ network.py                # MagicDNS URL settings and safe URL builder
│  ├─ operations/              # backup / retention / audit / incident workflows
│  └─ ui/                      # Streamlit Web Operations Console
├─ config/                     # versioned, non-secret operational configuration
│  ├─ network.json              # shared hostname, distinct Main/Analytics ports
│  └─ retention_policy.json
├─ setup/                      # runtime/dev dependencies and venv bootstrap
├─ .streamlit/                 # browser console defaults (loopback by default)
├─ assets/                     # versioned brand and topology images
├─ scripts/                    # Windows task registration and restart helpers
├─ Documents/                  # Japanese operational documentation
├─ tests/                      # deterministic, network-free tests
├─ analytics_web.py            # compatibility entry point
├─ health.py / backup.py ...   # compatibility entry points for existing operations
└─ run_*.bat                   # operator-facing launchers
```

## 配置ルール

- 新しい監視・状態観測は`smai_analytics/monitoring/`へ追加します。
- バックアップ、保持、監査、障害調査の運用処理は`smai_analytics/operations/`へ追加します。
- 表示だけを担当するStreamlit Web Operations Consoleコードは`smai_analytics/ui/`へ追加します。
- secretを含まない設定だけを`config/`へ置きます。Runtimeの状態、ログ、バックアップ、個人データはGit管理しません。
- 依存関係はルートではなく`setup/requirements*.txt`へ置きます。
- ルート互換入口を削除・改名する場合は、Scheduler、自動起動、README、運用ガイド、テストの契約を先に更新し、旧起動経路が不要であることを確認します。

## 起動契約

通常の起動・確認コマンドは次のとおりです。

```powershell
run_analytics_web.bat
python health.py
python backup.py create
python retention.py --dry-run
```

ブラウザー画面は`run_analytics_web.bat`で起動します。通常アクセスは`config/network.json`から解決するMagicDNS URLの`http://desktop-bqrpr4c:8502`であり、サーバーPC内の確認は`http://localhost:8502`です。Main Applicationの`http://desktop-bqrpr4c:8501`とは同じホスト名・異なるポートで区別します。直接の`streamlit run analytics_web.py`はloopback（`127.0.0.1:8502`）が既定で、`0.0.0.0`待受は明示的なバッチ起動だけが行います。`0.0.0.0`は待受先であり、ブラウザーで開くURLではありません。
