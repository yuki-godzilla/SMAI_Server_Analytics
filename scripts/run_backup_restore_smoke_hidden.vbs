Option Explicit

Dim shell, filesystem, powershell, runner, command, exitCode

Set shell = CreateObject("WScript.Shell")
Set filesystem = CreateObject("Scripting.FileSystemObject")
powershell = shell.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\WindowsPowerShell\v1.0\powershell.exe"
runner = filesystem.BuildPath(filesystem.GetParentFolderName(WScript.ScriptFullName), "run_backup_restore_smoke.ps1")

If Not filesystem.FileExists(powershell) Or Not filesystem.FileExists(runner) Then
    WScript.Quit 1
End If

command = Chr(34) & powershell & Chr(34) & " -NoProfile -ExecutionPolicy Bypass -File " & Chr(34) & runner & Chr(34)
exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode
