# Work Log

## 2026-07-16

- 承認制Codex Autofix v2（実装）
  - 変更: `auto_merged_pending_deploy`後に同じ40桁commit hashを指定する30分の第3承認を追加した。配備承認はマージ承認と別リースであり、通知メールや画面閲覧を承認として扱わない。
  - 変更: Analytics所有者のInteractive limited tokenで動く別配備executorを追加した。target branch／HEAD／parent／clean、利用中セッション、実行中処理、fresh healthy snapshot、決定的テスト、新規backup manifestを検証し、成功時だけAnalyticsを再起動する。
  - 変更: 再起動後90秒以内のhealth endpointとページ到達確認に失敗した場合、exact repair commitを`git revert`するrollback commitを作成し、Analyticsだけを再起動して復旧を確認する。成功は`auto_rolled_back`、失敗は`auto_rollback_failed`として最優先通知する。
  - 変更: `SMAI-Codex-Autofix-Deploy`の1分周期・`IgnoreNew`・15分上限Task登録／解除スクリプト、状態表示、鮮度監視、Gmail通知、運用手順を追加した。Incident、Codex worker、配備executorの反復triggerは日をまたいで継続するDaily＋日内repetitionへ統一した。`deployment_enabled=false`を既定とした。
  - 検証: 隔離した実Gitリポジトリで、第3承認hash照合、正常配備、利用中preflight停止、health失敗からのrevert commitと復旧、rollback失敗、deploy worker dry-runを確認した。
  - 未実施: live task登録、実プロセス再起動ドリル、実Gmail配送、`deployment_enabled=true`は実機権限・外部送信を伴うため実施していない。

## 2026-07-15

- 承認制Codex Autofix v1（実装）
  - 変更: critical Incidentに対する24時間の第1承認、隔離Git worktreeでの`codex exec --sandbox workspace-write`、allowlist／機微情報／構造化結果／決定的テスト検査、単一local修復commitを実装した。
  - 変更: 修復準備完了レポートの管理者通知後、40桁commit hashを指定する1時間の第2承認、clean target・基準HEAD・branch HEAD・commit parentを再検証するfast-forward限定マージを実装した。再起動とpushは自動化していない。
  - 変更: 承認、取消、実行、commit、マージ、失敗をRuntimeの状態JSONとappend-only JSONL、既存改善レポート、固定Gmail Outboxへ記録する。期限切れ、未許可パス、Schema不一致、機微情報、dirty target、hash差替えはfail-closedで停止する。
  - 変更: 専用標準Windowsアカウント向けの5分周期・`IgnoreNew`・45分上限Task登録／解除スクリプトを追加した。設定は`enabled=false` / `mode=dry_run`を既定とした。
  - 検証: 隔離した実Gitリポジトリで、修復commit、第2承認、fast-forward、期限切れ、取消、並行worker、commit不一致、dirty target、target HEAD変更、再承認、マージ後検証失敗を確認した。
  - 未実施: 専用WindowsアカウントとACL、Codexログイン、Task登録、実Gmail配送、実Codex dry-runドリル、active化はlive operationのため実施していない。

## 2026-07-14

- 障害通知・管理者承認ワークフロー（実装）
  - 変更: critical障害のローカル調査依頼と改善レポートを起点に、固定Gmailへの管理者通知、未復旧時の15分再通知、healthy復帰時の復旧通知、配送失敗の最大3回再試行を追加した。送信先はRuntime設定、GmailアプリパスワードはWindows Credential Managerの`SMAI-Analytics-Gmail-SMTP`だけへ保存する。メールアドレス・パスワードはWeb Console、Git、ログ、outboxへ残さない。
  - 変更: 管理者が`approve-codex`を実行した場合だけ、Runtimeに承認済みCodex修正依頼を発行するようにした。依頼には実画面での修正確認、他機能の影響調査、管理者向け修正報告、承認前のコード変更禁止を明記した。Codex実行・外部送信はこの承認証跡だけでは開始しない。
  - 未実施: Googleの2段階認証・アプリパスワードと固定宛先はまだ提供されていないため、Credentialの保存、実メール送信、Windowsタスク登録は実行していない。

- 実画面UIレビュー第1回（概要 / 通常デスクトップ幅 1920px / healthy）をChromeで実施
  - 観察: health score、現在状態、Next Checkの導線は最初の画面で確認できた。一方、状態表示と説明見出しに英日混在があり、運用判断の読み順が分散していた。
  - 変更: OverviewのKPI、健全性カード、確認導線、サービス概要とサービス説明を日本語の運用語へ統一した。
  - 再確認: Analyticsのみを再起動し、health endpointの`200 / ok`と同一幅のOverviewで、ヘルススコア、現在の実行状態、次に確認、サービス概要の表示を確認した。
- 実画面UIレビュー第2回（推移 / 通常デスクトップ幅 1920px / 隔離したdegradedテストRuntime）をChromeで実施
  - 観察: L2の失敗はCheck Matrixの白文字だけで、黄色の全体状態に埋もれていた。履歴が未収集であることは明示され、正常扱いされていなかった。
  - 変更: 最新Check Matrixの直前に、失敗・重大、要確認・期限超過、不明の件数をfail-closedで要約する状態色付きアラートを追加した。
  - 再確認: 隔離環境の同一degraded状態で、失敗・重大 1件が赤いアラートとして表の直前に表示され、対象行を追えることを確認した。通常のAnalyticsも再起動後にhealth endpointの`200 / ok`を確認した。
- 実画面UIレビュー第3回（セッション・改善レポート / 通常デスクトップ幅 1920px / healthy）をChromeで実施
  - 観察: ヘッダーの「接続セッション 1」と端末別の現在接続「0台」が並び、観測済みセッションと現在接続の違いが読み取りにくかった。改善レポートでは復元検証・最小空き率・履歴カバレッジと空状態の説明を一画面で確認できた。
  - 変更: ヘッダーを90秒以内の現在接続数へ変更し、観測セッション数を補足として明示した。
  - 再確認: Analyticsのみを再起動し、同じhealthy状態で「現在接続 0」「観測セッション 1件 / 90秒以内」と端末別の0台表示が一致して理解できることを確認した。
- 実画面UIレビュー第4回（概要・障害・タスク・ログ / 通常デスクトップ幅 1920px / healthyおよび隔離したcriticalテストRuntime）をChromeで実施
  - 観察: 従来のOverviewは大型のカードが連続し、現在の判断、次の確認先、サービス状態を読む視線が分かれていた。critical状態では上部KPIの状態説明に上向き矢印が表示され、障害を増加と誤読できる余地があった。
  - 変更: 小さなアプリバー、罫線で区切るKPIストリップ、状態コマンド行、3サービスの状態行、詳細タブへのインライン導線へ再構成した。KPIの状態説明は増減表示を使わない補足テキストに変更した。
  - 再確認: ChromeでhealthyのOverviewと、隔離したcritical状態のOverview・障害・タスク・ログを確認した。criticalでは「18 / 100」「重大」と赤いサービス状態・障害導線が矛盾なく表示され、カードの連続なしに障害箇所を追えることを確認した。Analyticsのみ再起動後、health endpointの`200 / ok`も確認した。
- 実画面UIレビュー第5回（概要・推移 / 狭幅390px / healthyおよび隔離したdegradedテストRuntime）をChromeで実施
  - 観察: 狭幅ではアプリバーのコンテキストを省き、状態、更新、KPI、タブを優先して縦に並べる必要があった。degradedの推移では失敗要約と検査表の先頭が、横方向のレイアウト崩れなく到達できた。
  - 変更: 第4回のレスポンシブ規則により、KPIを縦並び、状態コマンド行を一列、詳細導線を縦並びにした。追加の画面要素や書き込み操作は導入していない。
  - 再確認: ChromeでhealthyのOverview、隔離したdegradedの推移タブを実際に選択し、状態pill、`100 / 100`、`62 / 100`、失敗・重大1件の要約、検査表の先頭を確認した。
- 実画面UIレビュー第6回（ヘッダー / 通常デスクトップ幅 1920px / healthy）をChromeで実施
  - 観察: 高密度化後のヘッダーは状態を素早く読める一方、盾だけの小アイコンではAnalytics用途が伝わりにくく、以前のマスコットも表示されなくなっていた。
  - 変更: 盾と下部の大きな`SMAI Analytics`プレートを重ねた正方形アイコンを生成して左上に配置した。右上の状態pillの隣に運用マスコットを復帰し、状態判定は従来どおりpillと状態色を正とした。
  - 再確認: Analyticsのみ再起動後、Chromeで新アイコン、`SMAI Analytics`の表記、マスコット、正常状態pillを同じヘッダー内で確認した。health endpointの`200 / ok`も確認した。
- 実画面UIレビュー第7回（DashBoard / 通常デスクトップ幅 1920px / healthyおよび隔離したdegradedテストRuntime）をChromeで実施
  - 観察: 従来の概要は現在状態とサービス一覧には到達しやすい一方、端末接続、healthの変化、応答・容量・タスクの根拠を一度に把握できなかった。
  - 変更: 先頭タブを`DashBoard`へ改名し、server・PC・スマートフォン・タブレットのライブ接続トポロジー、記録済みhealthによるHealth 24H、応答p95・容量のマイクロ推移、L1〜L3・応答・容量・タスク鮮度の重要シグナルを追加した。pulseは90秒以内のheartbeatの現在性を表すだけで通信量ではない。Datadog、Amazon CloudWatch、Grafanaの公式ダッシュボード資料を参照し、概要から詳細タブへ掘り下げる構成を採用した。
  - 再確認: healthyではデスクトップの実接続1台に対応するPCへのpulseが時間差スクリーンショットで移動し、Health 24H、応答p95、最小空き率を確認した。隔離したdegradedではserver・未観測端末を要確認、L2失敗を重要シグナルとして表示し、履歴なしを正常線で補間しない空状態を確認した。Analyticsのみ再起動後、health endpointの`200 / ok`を確認した。
- 実画面UIレビュー第8回（DashBoard / 狭幅390px / 隔離したdegradedテストRuntime）をChromeで実施
  - 観察: 狭幅ではKPI、状態判断、トポロジー、履歴、根拠シグナルが横スクロールや重なりなく、縦の読み順で到達できる必要があった。
  - 再確認: Chromeの390px幅で、KPIと状態判断が縦並びになり、server・PC・スマートフォン・タブレットの各ノード、Health 24Hの履歴欠損表示、L1〜L2の重要シグナルが表示領域内に収まることを確認した。
- 実画面UIレビュー第9回（DashBoardヘッダー・ライブ接続トポロジー / 実装前確認）
  - 観察: `DashBoard`のライブ接続トポロジーは画像資産ではなく小さな文字ボックスになっていた。ヘッダーは既存の正方形アイコンとマスコットを使っているが、運用画面の識別子としては小さかった。またStreamlitのbrowser page iconは汎用の📡で、ブラウザタブ／追加アプリの識別に既存の`SMAI Analytics`アイコンを使えていなかった。
  - 変更: 既存のserver・PC・スマートフォン・タブレット画像をライブ接続トポロジーへ復帰し、文字ボックスを廃止した。ヘッダーの画像ファイルは変えずにアイコンとマスコットを拡大し、同じ既存アプリアイコンをStreamlitのpage iconへ指定した。
  - 再確認: Analyticsのみを再起動し、health endpointの`200 / ok`を確認した。Chromeの通常デスクトップ幅で、既存の正方形`SMAI Analytics`アイコンとマスコットが拡大されたヘッダー、既存画像を使うserver・PC・スマートフォン・タブレットの接続トポロジー、現在接続に対応するpulseを確認した。
- 実画面UIレビュー第10回（DashBoard Health Score / 実装前確認）
  - 観察: 状態コマンドのHealth Scoreは円形の外枠と数値だけで、以前のドーナツ型ゲージよりも値と状態色の対応が弱かった。
  - 変更: Health Scoreを現在の状態色で塗る`0〜100`のドーナツ型ゲージへ戻し、中央の数値を維持した。`unknown`は0点の灰色リングとしてfail-closedに表示する。
  - 再確認: Analyticsのみを再起動し、health endpointの`200 / ok`を確認した。Chromeの通常デスクトップ幅で、health `100`が緑のドーナツ型ゲージと中央の数値として表示されることを確認した。Streamlitが要素のインラインstyleを除去するため、状態と割合はCSSクラスで与え、ブラウザが計算した背景に`conic-gradient`が設定されることも確認した。
- 実画面UIレビュー第11回（DashBoardヘッダー・可視化領域 / 実装前確認）
  - 観察: 正方形アプリアイコンはブラウザタブ用には適しているが、ヘッダーの元の横長ロゴではなかった。ヘッダー、ライブ接続トポロジー、Health 24Hの縦幅が小さく、画像・折れ線・状態情報を読む余白が不足していた。
  - 変更: ヘッダーを元の横長`SMAI Analytics`ロゴへ戻し、ヘッダー高を約3倍、ロゴ・マスコット・状態表示・更新操作を拡大した。ライブ接続トポロジーとHealth 24Hは、画像、接続経路、時系列、マイクロ推移が詰まらない縦幅へ拡張した。
  - 再確認: Analyticsのみを再起動し、health endpointの`200 / ok`を確認した。Chromeの通常デスクトップ幅で、透明背景の元ワードマーク、拡大されたマスコット・状態pill・更新操作、440pxの接続トポロジー、拡張したHealth 24Hと応答／容量のマイクロ推移を確認した。透明PNGの余白は表示時にトリミングし、画像そのものが大きく見えるようにした。
- 実画面UIレビュー第12回（DashBoardライブ接続トポロジー / 実装前確認）
  - 観察: heartbeatを観測したPC経路にも、待機端末と同じ点線が残っていた。1個だけのpulseでは、接続の現在性は読めても、serverとの往復するデータ通信を直感的に読み取りにくかった。
  - 変更: 90秒以内のheartbeatを観測した端末だけを実線と淡い発光レーンに変更し、server→端末と端末→serverへ移動する2個の粒子を追加した。待機・期限超過・観測不能の経路は点線を維持し、reduced motion設定では粒子を停止する。粒子は通信量・内容ではなくheartbeat通信の現在性を表すことを説明文で明示した。Grafana Node graphの関係線表現を参照した。
  - 再確認: Analyticsのみを再起動し、health endpointの`200 / ok`を確認した。Chromeの通常デスクトップ幅で、現在接続1台のPC経路だけが緑の実線・発光レーンになり、2個の粒子が逆方向へ移動することを確認した。スマートフォンとタブレットの待機経路は点線のまま残った。StreamlitがSVG要素のinline CSS変数を除去することを実画面で検出したため、状態色はCSSクラスへ移し、実線・発光・粒子の表示が確実に適用されることも確認した。
- 実画面UIレビュー第13回（DashBoardヘッダー・可視化余白 / 通常デスクトップ幅）
  - 観察: Server画像下のラベルに中央の通信経路が重なり、名称・状態と経路を同時に読み取りにくかった。ライブ接続トポロジーとHealth 24Hは前版より改善したが、画像と推移を読む縦方向の余白をさらに確保したい。ヘッダーの盾は十分に識別できる一方、`SMAI Analytics`の文字は相対的に小さかった。
  - 変更: Serverラベルを画像左側へ移し、狭幅だけは画像下へ戻すレスポンシブ規則を追加した。トポロジーを440pxから528px、Health 24H本体を166pxから200px、マイクロ推移を78pxから94pxへそれぞれ20%拡張し、接続経路のSVG座標も追従させた。画像生成で大きな文字の横長ロゴを作成し、元ロゴから切り出した盾をピクセル単位で保持したまま、文字部分だけを従来の約2倍の高さで合成した透過PNGへ差し替えた。
  - 再確認: Analyticsのみを再起動し、health endpointの`200 / ok`を確認した。Chromeの通常デスクトップ幅で、Serverラベルは画像左側、通信線はその下へ分離され、ラベル領域`y=840〜912`と実線領域`y=932〜1201`が重ならないことを確認した。トポロジー528px、Health本体200px、マイクロ推移94px、新しい大きな`SMAI Analytics`文字と従来と同じ盾が表示されることを確認した。
- 実画面UIレビュー第14回（DashBoard Health 24Hの未使用領域 / 通常デスクトップ幅）
  - 観察: Health 24Hの`visual-surface`は480pxで終わり、同じ行のライブ接続トポロジーは674pxだった。Health履歴の下とマイクロ推移の下に計194pxの未使用領域があり、右カラムの高さを活用できていなかった。
  - 変更: Health 24Hをトポロジーと同じ最小674pxのflexレイアウトに変更し、Health履歴と応答p95・最小空き率のマイクロ推移ブロックを等しいflex比で配分した。Health scoreは記録済みの値を0〜100の下端まで淡く塗る面グラフとし、100点を空白ではなく満たされた健全性として読めるようにした。欠損時も正常な面や線を作らない。
  - 再確認: Analyticsのみを再起動し、health endpointの`200 / ok`を確認した。Chromeの通常デスクトップ幅で、ライブ接続トポロジーとHealth 24Hがともに674px、Health履歴260px、補助推移ブロック277pxとなり、罫線・余白を含めたコンテンツ領域がほぼ半分ずつ使われることを確認した。Health 100の緑線と0〜100を表す淡い面、応答・容量のマイクロ推移が同じHealthパネル内に表示された。
- 実画面UIレビュー第15回（DashBoard Health 24Hの上・下領域配分 / 通常デスクトップ幅）
  - 観察: 前回のflex配分は履歴SVGと補助推移だけを対象にしており、Health 24Hの見出し・score行が上段の追加高さになっていた。そのため、計測値が近くても、面グラフ側が補助推移側より大きく見えた。
  - 変更: Health 24Hの見出し・score・履歴を`health-history-block`へまとめ、下段には`health-micro-block`を追加して同じ`flex: 1`の兄弟要素にした。上下の区切りはパネルの`gap`として一度だけ適用し、下段の罫線・内側余白は等分した外枠の内部で使う。これにより下段の15pxの内側余白が外枠高さへ加算されず、上・下とも厳密に同じ高さになる。
  - 再確認: Analyticsのみを再起動し、health endpointの`200 / ok`を確認した。Chromeの通常デスクトップ幅で、Health 24H全体は674px、見出し・score・履歴を含む上段は307px、応答・容量の補助推移を含む下段も307px、両者の間隔は15pxとなることをDOMの実測と画面表示で確認した。
- 実画面UIレビュー第16回（DashBoard Health 24Hの狭幅領域配分）
  - 観察: 狭幅用規則が`health-history-block`だけに220pxの最小高さを与え、Healthパネル全体の高さは内容任せだった。上段・下段の外枠をデスクトップで等分しても、狭幅では上段が下段より大きくなる。
  - 変更: 狭幅のHealth 24Hを560px高のflexコンテナへ固定し、上段・下段とも最小高さを0へ統一した。既存の同じflex比と15pxの区切りを使うため、幅760px以下でも上・下の外枠を等分する。
- 実画面UIレビュー第17回（スマホ／タブレット responsive 改善スプリント・第1回）
  - 観察: 共有されたiPhone実機画面で、ヘッダーの横長ロゴとマスコットが縦に大きく積まれ、更新ボタンが白背景になっていた。KPIは1列の長い列となり、補足文字のコントラストも不足していた。ホーム画面へ追加したショートカットには、ブラウザfaviconだけではアイコンが表示されなかった。
  - 変更: 本家SMAIと同じ`max-width: 767px`／`768px–1024px`／`1025px+`の契約へ揃えた。スマホではKPIを2列、操作を44px以上、タブを局所横スクロール、ヘッダーをロゴ42px・マスコット56px・コンパクトな状態行へ再構成した。DashBoardのトポロジーとHealth 24Hも360px／460pxへ圧縮し、Healthの上・下等分は維持する。タブレットでは通常のStreamlit列を2列へ折り返し、900px以下のトポロジー／Healthは1列にする。既存の正方形ロゴからApple Touch Icon 180pxとPWAアイコン192px／512pxを生成し、JSON MIME typeで提供できる専用コンポーネント経由でmanifestとApple向けhead metadataを追加した。
  - 再確認: Analyticsのみを再起動し、health endpoint、Apple Touch Icon、192px／512px PWAアイコン、manifestの各URLがすべて`200`、manifestが`application/json`であることを確認した。Chrome実画面で、`apple-touch-icon`、manifest、PWAアプリ名、theme colorがheadへ登録され、通常幅にページ横スクロールがないこと、更新ボタンが濃紺背景、KPI補足文字が可読色で表示されることを確認した。更新後の実機iPhone／iPad幅の視覚受け入れは次回確認する。
- 実画面UIレビュー第18回（推移の表・チャート / iPhone実機フィードバック）
  - 観察: 共有されたiPhone実機画面では、最新Check MatrixがPC幅の4列データグリッドのまま表示され、右端の詳細が隠れていた。Health、応答、容量、タスク鮮度の標準line chartも白いキャンバス、密な縦書き日時、判読しにくい凡例となり、深いネイビーの運用画面から浮いていた。
  - 変更: 全ての読み取り専用表を、PCでは罫線付きの運用表、767px以下では項目名を左・値を右に保つ44px以上の縦長証跡カードへ統一した。推移は白い標準チャートを廃止し、暗色のAltair時系列、4本程度の時刻tick、タップtooltip、状態に対応する系列色へ変更した。Streamlitテーマも同じネイビー基調へ明示し、選択欄・チャートの背景をアプリ全体と統一した。
  - 再確認: healthy/degraded/critical/high-volume/recoveryの合成5状態で全8タブをレンダリングし、Chrome実画面で証跡表、4つの暗色時系列、ページ横スクロールなし、0px高のPWA metadataコンポーネントを確認した。実機のスマホ・タブレットでの最終受け入れは、更新後に同じ画面を開いて確認する。

## 2026-07-13

- Overviewを「現在の安全性と次の確認先」に絞り、時系列・検査表・復元準備・端末別詳細を推移、改善レポート、セッションへ分散
- overall状態とTask鮮度に応じて、確認すべきタブを決定的に案内するNext Checkを追加
- healthy、degraded、critical、高件数、復旧後の5状態をStreamlitレンダラーで再確認
- Tkinter版を廃止し、`analytics_web.py`を正規のWeb Operations Console入口へ統一
- Overview、推移、セッション、操作履歴、障害、改善レポート、タスク、ログの8画面をWeb版へ実装
- 共有されたChrome全画面を確認し、4K／通常モニター向けにコンテンツ幅、カード内の画像配置、文字・余白、timelineのラベル密度を改善
- healthy、degraded、critical、高負荷、復旧後の5状態をStreamlitの実レンダラーで検証
- `run_analytics_web.bat`、`restart_analytics_web.bat`、Interactive AtLogOn自動起動タスクをWeb版へ統一し、TCP 8502の起動・health・HTML配信・タスク設定を確認
- Tkinter実装、旧ランチャー、旧再起動スクリプト、旧UIテストを削除

## 2026-07-12

- `telemetry.py` を追加し、health snapshotを日別の生記録と5分集計へ分離して永続化
- Streamlit health/page、TCP、L3保存チェックの所要時間と、SMAIデータ／Runtimeの容量ヘッドルームをhealth snapshotへ追加
- OverviewへRecovery Readiness、`推移`画面へL1〜L3状態履歴、応答時間p95、容量推移を追加
- 24時間・7日・30日の推移表示で、観測欠損を`unknown`として可視化し、正常率に含めないようにした
- Tkinter実画面の全8タブを対象に、標準・ノートPC相当・狭幅の3回のUI妥当性検証スプリントを実施
- 第1回で高DPI時のブランド領域過大を確認し、狭幅ではテキスト見出しと状態・最終確認時刻を優先する表示へ改善
- 第2回で狭幅のタブ到達性と推移下段の到達性を確認し、短縮タブ名と推移ページの縦スクロールを追加
- 第3回で全画面と推移下段の到達性を再確認
- Windows Task Schedulerの最終実行、次回予定、最終結果、実行パスをRuntimeへ5分ごとまたは状態変化時に記録する`task_monitor.py`を追加
- Tasksへ鮮度・最終実行・次回予定・判定理由を追加し、TrendsへJOB FRESHNESSを追加

## 2026-07-11

- SMAI本体と運用監視を分離するため、`SMAI_Server_Analytics` リポジトリを作成
- GitHub `yuki-godzilla/SMAI_Server_Analytics` のmainへ初期push
- Tkinter監視画面、L1〜L3ヘルスチェック、Runtimeログ方針を追加
- 本体の銘柄更新成果物は正式マスターとmanifestのみ自動commit/pushする方針を採用
- raw、cache、日付別レポートは生成物としてRuntimeまたはignored領域に置く方針を採用
- 実画面を用いたUI妥当性評価を実施し、Overviewのservice topology、health gauge、timeline、check matrixを確認
- Sessions、Activity History、Incidents、Tasks、Logsを「要約と可視化を上段、詳細を下段」の構成へ改善
- セッションID短縮、heartbeat相対時刻、空状態の説明、Windows Taskのunknown表示、ログ重要語集計を追加
- SMAI本体のマスコット画像を参照し、Analytics専用の運用監視マスコットを生成
- heartbeat、health、status bar、shieldをモチーフにしたAnalytics専用ロゴを生成
- シールドと「SMAI Analytics」のアプリ名を一体化した横長ワードマークを追加
- `dashboard.py` のヘッダー左側へロゴ、右側の状態表示へマスコットを配置
- 画像欠損時もテキストUIで起動を継続するフォールバックを追加
- TkinterのWindows DPI scalingを明示し、PillowのLANCZOS縮小と2倍密度ヘッダー画像のフォールバックを追加
- 全TreeviewとLogsへ縦・横スクロールバーを追加
- Activity Historyの結果・ユーザー・操作フィルター、Incidentsの重要度フィルター、該当なし表示を追加
- activity state欠損時にセッション数・処理数を正常な0と誤表示しないよう改善
- 4Kヘッダー向けにワードマーク上下余白をトリミングし、太字・大サイズ表示へ更新
- 元のSMAIマスコットの世界観を維持した眼鏡付きアナリスト版へ差し替え、背景を透過PNG化
- 4K／高DPI時はUI scaling倍率に応じて元画像から読み込み、低DPI時は2倍密度画像へフォールバックする表示経路を追加
