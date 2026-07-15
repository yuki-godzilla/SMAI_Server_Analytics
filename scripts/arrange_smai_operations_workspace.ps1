[CmdletBinding()]
param(
    [ValidateRange(0, 180)]
    [int]$MaxWaitSeconds = 90,

    [ValidateRange(1, 10)]
    [int]$PollSeconds = 2
)

# Keep the operations workspace predictable after interactive logon.  The
# script only targets the six named SMAI windows; unrelated windows are never
# moved or restacked.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms

if (-not ("SmaiOperationsWorkspace.NativeWindow" -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace SmaiOperationsWorkspace
{
    public static class NativeWindow
    {
        public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

        public const int SW_RESTORE = 9;
        public const uint SWP_NOACTIVATE = 0x0010;
        public const uint SWP_SHOWWINDOW = 0x0040;
        public static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
        public static readonly IntPtr HWND_NOTOPMOST = new IntPtr(-2);
        public static readonly IntPtr HWND_BOTTOM = new IntPtr(1);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool IsWindowVisible(IntPtr hWnd);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        public static extern int GetWindowTextLength(IntPtr hWnd);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);

        [DllImport("user32.dll")]
        public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool ShowWindow(IntPtr hWnd, int command);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool SetWindowPos(
            IntPtr hWnd,
            IntPtr hWndInsertAfter,
            int x,
            int y,
            int width,
            int height,
            uint flags);
    }
}
'@
}

function Get-VisibleTopLevelWindows {
    $windows = [System.Collections.Generic.List[object]]::new()
    $callback = [SmaiOperationsWorkspace.NativeWindow+EnumWindowsProc] {
        param([IntPtr]$Handle, [IntPtr]$Unused)

        if (-not [SmaiOperationsWorkspace.NativeWindow]::IsWindowVisible($Handle)) {
            return $true
        }

        $titleLength = [SmaiOperationsWorkspace.NativeWindow]::GetWindowTextLength($Handle)
        if ($titleLength -eq 0) {
            return $true
        }

        $titleBuilder = [System.Text.StringBuilder]::new($titleLength + 1)
        [void][SmaiOperationsWorkspace.NativeWindow]::GetWindowText($Handle, $titleBuilder, $titleBuilder.Capacity)

        [uint32]$processId = 0
        [void][SmaiOperationsWorkspace.NativeWindow]::GetWindowThreadProcessId($Handle, [ref]$processId)
        try {
            $processName = (Get-Process -Id $processId -ErrorAction Stop).ProcessName
        } catch {
            $processName = $null
        }

        $windows.Add([pscustomobject]@{
                Handle = $Handle
                ProcessName = $processName
                Title = $titleBuilder.ToString()
            })
        return $true
    }

    [void][SmaiOperationsWorkspace.NativeWindow]::EnumWindows($callback, [IntPtr]::Zero)
    return @($windows)
}

function Get-HalfScreenRectangle {
    param(
        [Parameter(Mandatory)]
        [System.Drawing.Rectangle]$WorkingArea,

        [Parameter(Mandatory)]
        [ValidateSet("Left", "Right")]
        [string]$Side
    )

    $leftWidth = [math]::Floor($WorkingArea.Width / 2)
    if ($Side -eq "Left") {
        return [pscustomobject]@{
            X = $WorkingArea.X
            Y = $WorkingArea.Y
            Width = $leftWidth
            Height = $WorkingArea.Height
        }
    }

    return [pscustomobject]@{
        X = $WorkingArea.X + $leftWidth
        Y = $WorkingArea.Y
        Width = $WorkingArea.Width - $leftWidth
        Height = $WorkingArea.Height
    }
}

function Set-SmaiWindowLayout {
    param(
        [Parameter(Mandatory)]
        [IntPtr]$Handle,

        [Parameter(Mandatory)]
        [pscustomobject]$Rectangle,

        [Parameter(Mandatory)]
        [ValidateSet("Topmost", "Bottom", "Normal")]
        [string]$Stacking
    )

    $insertAfter = switch ($Stacking) {
        "Topmost" { [SmaiOperationsWorkspace.NativeWindow]::HWND_TOPMOST }
        "Bottom" { [SmaiOperationsWorkspace.NativeWindow]::HWND_BOTTOM }
        "Normal" { [SmaiOperationsWorkspace.NativeWindow]::HWND_NOTOPMOST }
    }

    [void][SmaiOperationsWorkspace.NativeWindow]::ShowWindow($Handle, [SmaiOperationsWorkspace.NativeWindow]::SW_RESTORE)
    $flags = [SmaiOperationsWorkspace.NativeWindow]::SWP_NOACTIVATE -bor [SmaiOperationsWorkspace.NativeWindow]::SWP_SHOWWINDOW
    if (-not [SmaiOperationsWorkspace.NativeWindow]::SetWindowPos(
            $Handle,
            $insertAfter,
            $Rectangle.X,
            $Rectangle.Y,
            $Rectangle.Width,
            $Rectangle.Height,
            $flags)) {
        throw "SetWindowPos failed for handle $Handle."
    }
}

$primaryScreen = [System.Windows.Forms.Screen]::AllScreens | Where-Object Primary | Select-Object -First 1
$secondaryScreen = [System.Windows.Forms.Screen]::AllScreens |
    Where-Object { -not $_.Primary } |
    Sort-Object { $_.WorkingArea.X }, { $_.WorkingArea.Y } |
    Select-Object -First 1

if ($null -eq $primaryScreen -or $null -eq $secondaryScreen) {
    throw "A primary display and one secondary display are required to arrange the SMAI workspace."
}

$mainLeft = Get-HalfScreenRectangle -WorkingArea $primaryScreen.WorkingArea -Side Left
$mainRight = Get-HalfScreenRectangle -WorkingArea $primaryScreen.WorkingArea -Side Right
$secondaryLeft = Get-HalfScreenRectangle -WorkingArea $secondaryScreen.WorkingArea -Side Left
$secondaryRight = Get-HalfScreenRectangle -WorkingArea $secondaryScreen.WorkingArea -Side Right

$targets = @(
    [pscustomobject]@{
        Name = "SMAI Main App VS Code"
        Rectangle = $mainLeft
        Stacking = "Topmost"
        Matches = { param($window) $window.ProcessName -eq "Code" -and $window.Title -like "*Smart_Market_AI*" }
    },
    [pscustomobject]@{
        Name = "SMAI Analytics VS Code"
        Rectangle = $mainRight
        Stacking = "Topmost"
        Matches = { param($window) $window.ProcessName -eq "Code" -and $window.Title -like "*SMAI_Server_Analytics*" }
    },
    [pscustomobject]@{
        Name = "SMAI Main Application Prompt"
        Rectangle = $mainLeft
        Stacking = "Bottom"
        Matches = { param($window) $window.Title -eq "SMAI Main Application Prompt" }
    },
    [pscustomobject]@{
        Name = "SMAI Analytics Prompt"
        Rectangle = $mainRight
        Stacking = "Bottom"
        Matches = { param($window) $window.Title -eq "SMAI Analytics Prompt" }
    },
    [pscustomobject]@{
        Name = "SMAI Main Application Web"
        Rectangle = $secondaryLeft
        Stacking = "Normal"
        Matches = { param($window) $window.ProcessName -eq "chrome" -and $window.Title -like "Smart Market AI*" }
    },
    [pscustomobject]@{
        Name = "SMAI Analytics Web"
        Rectangle = $secondaryRight
        Stacking = "Normal"
        Matches = { param($window) $window.ProcessName -eq "chrome" -and $window.Title -like "SMAI Analytics | Operations Console*" }
    }
)

$deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
$arranged = @{}
do {
    $windows = Get-VisibleTopLevelWindows
    foreach ($target in $targets) {
        $window = $windows | Where-Object { & $target.Matches $_ } | Select-Object -First 1
        if ($null -eq $window) {
            continue
        }

        Set-SmaiWindowLayout -Handle $window.Handle -Rectangle $target.Rectangle -Stacking $target.Stacking
        $arranged[$target.Name] = $true
    }

    if ($arranged.Count -eq $targets.Count -or (Get-Date) -ge $deadline) {
        break
    }
    Start-Sleep -Seconds $PollSeconds
} while ($true)

$missingTargets = $targets | Where-Object { -not $arranged.ContainsKey($_.Name) } | ForEach-Object Name
if ($missingTargets) {
    Write-Warning ("SMAI workspace layout skipped windows that were not ready: " + ($missingTargets -join ", "))
}
