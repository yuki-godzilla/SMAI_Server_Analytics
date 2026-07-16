[CmdletBinding()]
param(
    [string]$OutputDirectory = "C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime\development_environment\handover"
)

$ErrorActionPreference = "Stop"
$outputPath = Join-Path $OutputDirectory "SMAI-Codex-Autofix_引継ぎ指示書.docx"

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Add()
    $section = $document.Sections.Item(1)
    $section.PageSetup.TopMargin = 72
    $section.PageSetup.BottomMargin = 72
    $section.PageSetup.LeftMargin = 72
    $section.PageSetup.RightMargin = 72

    $normal = $document.Styles.Item(-1)
    $normal.Font.Name = "Calibri"
    $normal.Font.Size = 11
    $normal.ParagraphFormat.SpaceAfter = 6
    $normal.ParagraphFormat.LineSpacing = 15
    $normal.ParagraphFormat.Alignment = 0

    foreach ($styleId in @(-2, -3)) {
        $style = $document.Styles.Item($styleId)
        $style.Font.Name = "Calibri"
        $style.Font.Color = 11674146
        $style.ParagraphFormat.Alignment = 0
    }
    $document.Styles.Item(-2).Font.Size = 16
    $document.Styles.Item(-2).ParagraphFormat.SpaceBefore = 16
    $document.Styles.Item(-2).ParagraphFormat.SpaceAfter = 8
    $document.Styles.Item(-3).Font.Size = 13
    $document.Styles.Item(-3).ParagraphFormat.SpaceBefore = 12
    $document.Styles.Item(-3).ParagraphFormat.SpaceAfter = 6

    function New-DocumentParagraph([string]$Text) {
        $document.Content.InsertAfter("$Text`r")
        return $document.Paragraphs.Item($document.Paragraphs.Count - 1)
    }

    function Add-Paragraph([string]$Text, [int]$Size = 11, [bool]$Bold = $false, [int]$Color = 0) {
        $paragraph = New-DocumentParagraph $Text
        $paragraph.Range.Font.Name = "Calibri"
        $paragraph.Range.Font.Size = $Size
        $paragraph.Range.Font.Bold = [int]$Bold
        $paragraph.Range.Font.Color = $Color
        $paragraph.Range.ParagraphFormat.SpaceAfter = 6
        $paragraph.Range.ParagraphFormat.Alignment = 0
        return $paragraph
    }

    function Add-Heading([string]$Text, [int]$StyleId = -2) {
        $paragraph = New-DocumentParagraph $Text
        $paragraph.Range.Style = $StyleId
        $paragraph.Range.ParagraphFormat.Alignment = 0
        return $paragraph
    }

    function Add-Bullets([string[]]$Items) {
        foreach ($item in $Items) {
            $paragraph = Add-Paragraph $item
            $paragraph.Range.ListFormat.ApplyBulletDefault()
        }
    }

    function Add-Numbers([string[]]$Items) {
        foreach ($item in $Items) {
            $paragraph = Add-Paragraph $item
            $paragraph.Range.ListFormat.ApplyNumberDefault()
        }
    }

    $title = New-DocumentParagraph "SMAI-Codex-Autofix 引継ぎ指示書"
    $title.Range.Font.Name = "Calibri"
    $title.Range.Font.Size = 24
    $title.Range.Font.Bold = 1
    $title.Range.Font.Color = 0
    $title.Range.ParagraphFormat.Alignment = 0
    $title.Range.ParagraphFormat.SpaceAfter = 4

    $subtitle = Add-Paragraph "専用の限定権限アカウントで、安全に障害調査・修復支援を行うための運用手順" 12 $false 8355711
    $subtitle.Range.ParagraphFormat.SpaceAfter = 14
    $notice = Add-Paragraph "重要: 自動修復は初期状態で無効です。管理者承認・dry-run・正常性確認を通過するまで有効化しません。" 11 $true 192
    $notice.Range.Shading.BackgroundPatternColor = 15132390
    $notice.Range.ParagraphFormat.SpaceAfter = 14

    $null = Add-Heading "1. このアカウントの役割"
    $null = Add-Paragraph "SMAI-Codex-Autofix は、SMAI 本体の投資ロジックを変更せず、Server Analytics の障害調査・承認済み修復・結果報告を支援するための標準ユーザーです。管理者権限は持ちません。"
    Add-Bullets @(
        "SMAI 本体のランキング、スコア、Forecast、ユーザー画面の意味を変更しない。",
        "承認のない修復、マージ、配備を実施しない。",
        "認証情報、Cookie、API キー、.codex\\auth.json を他アカウントへコピーしない。"
    )

    $null = Add-Heading "2. 共通の開発環境"
    $null = Add-Paragraph "主アカウントとこの専用アカウントは、次の共通領域を使用します。VS Code 設定・拡張機能・Python 開発補助はここに集約されています。"
    $null = Add-Paragraph "C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime\development_environment" 10 $true 0
    Add-Bullets @(
        "VS Code 1.128.1、Python 3.12、Git、Codex CLI を利用可能。",
        "Python、Pylance、debugpy、PowerShell の VS Code 拡張機能を導入済み。",
        "開発環境を開く場合は、プロジェクト直下の scripts\\launch_smai_codex_autofix_workspace.ps1 を実行する。"
    )

    $null = Add-Heading "3. 初回ログインと Codex 認証"
    Add-Numbers @(
        "PowerShell を開き、whoami を実行して DESKTOP-BQRPR4C\\SMAI-Codex-Autofix であることを確認する。",
        '次を実行する: & "C:\Users\user\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe" login --device-auth',
        "ブラウザで同じ ChatGPT アカウントへサインインし、認証を完了する。パスワードや認証コードは記録・共有しない。",
        '次を実行して確認する: & "C:\Users\user\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe" login status'
    )
    $null = Add-Paragraph "補足: ChatGPT/Codex のログイン情報はアカウントごとに分離します。共通化するのは実行ファイルと開発環境であり、認証情報ではありません。" 10 $false 8355711

    $null = Add-Heading "4. 修復ワーカーの登録と安全確認"
    $null = Add-Paragraph "ワーカー登録は、管理者アカウントの PowerShell で専用アカウントのパスワードを入力して実施します。専用アカウント自身を管理者にしないでください。"
    Add-Numbers @(
        "登録前に Codex login status が正常であることを確認する。",
        "管理者 PowerShell で register_smai_codex_autofix_worker_task.ps1 を -UserId DESKTOP-BQRPR4C\\SMAI-Codex-Autofix 付きで実行する。",
        "SMAI-Codex-Autofix-Worker タスク、実行ユーザー、5分周期、45分上限、Limited 権限を確認する。",
        "config\\codex_autofix.json は enabled=false / dry_run のまま dry-run を確認する。",
        "承認済み Incident だけが処理対象になることを確認してから、管理者の明示承認で有効化する。"
    )

    $null = Add-Heading "5. 日常の確認項目"
    Add-Bullets @(
        "Analytics 画面で healthy / degraded / critical / unknown を確認する。",
        "障害通知メールの Incident ID、影響、承認要求、修復レポートを確認する。",
        "修復後は health snapshot、ログ、バックアップ、レポートが揃っていることを確認する。",
        "不明・破損・読み取り不能は正常扱いにせず、degraded または critical として扱う。"
    )

    $null = Add-Heading "6. 禁止事項"
    Add-Bullets @(
        "SMAI 本体の private module を Analytics から import しない。",
        "未承認の自動 push、任意コマンド実行、サービス停止、配備を行わない。",
        "秘密情報をファイル、ログ、メール、commit に保存しない。",
        "共通 Runtime フォルダ内の VS Code 設定は利用してよいが、認証情報を置かない。"
    )

    $null = Add-Heading "7. 困ったときの連絡・復旧順序"
    Add-Numbers @(
        "自動修復を開始せず、Analytics の状態と直近 Incident を確認する。",
        "管理者へ Incident ID、確認時刻、影響、ログ要約を通知する。",
        "承認がない場合は調査結果と推奨手順だけを報告する。",
        "修復実行後は成功・失敗・ロールバック・手動対応要否をレポートに残す。"
    )

    $null = Add-Heading "8. 初回確認記録"
    $null = Add-Paragraph "完了日: ____________________    確認者: ____________________" 11 $true 0
    Add-Bullets @(
        "専用アカウントで whoami を確認した。",
        "Codex login status が認証済みであることを確認した。",
        "共通の VS Code 開発環境を起動した。",
        "修復ワーカー登録と dry-run の結果を管理者が確認した。"
    )

    $footer = $section.Footers.Item(1).Range
    $footer.Text = "SMAI Server Analytics | 専用アカウント運用 | 2026-07-17"
    $footer.Font.Name = "Calibri"
    $footer.Font.Size = 9
    $footer.Font.Color = 8355711

    $document.SaveAs2($outputPath, 16)
    Write-Host "[OK] Created: $outputPath"
}
finally {
    if ($document) {
        $document.Close([ref]0)
    }
    if ($word) {
        $word.Quit()
    }
}
