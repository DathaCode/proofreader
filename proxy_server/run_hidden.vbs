' run_hidden.vbs - start the Sinhala proxy with NO visible window.
' Output is appended to data\server.log so you can still check activity.
Option Explicit
Dim fso, sh, here, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here
If Not fso.FolderExists(here & "\data") Then fso.CreateFolder(here & "\data")
' -u : unbuffered. Without it Python buffers stdout when it is redirected
'      to a file, so data\server.log stays EMPTY and is useless for
'      diagnosing a server that will not start.
cmd = "cmd /c py -u proxy.py >> """ & here & "\data\server.log"" 2>&1"
' 0 = hidden window, False = do not wait
sh.Run cmd, 0, False
