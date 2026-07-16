Option Explicit

Dim shell, index, command, exitCode

If WScript.Arguments.Count = 0 Then
    WScript.Quit 1
End If

command = ""
For index = 0 To WScript.Arguments.Count - 1
    command = command & " " & QuoteArgument(CStr(WScript.Arguments(index)))
Next

Set shell = CreateObject("WScript.Shell")
exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode

Function QuoteArgument(value)
    QuoteArgument = Chr(34) & Replace(value, Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function
