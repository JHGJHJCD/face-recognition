# מודד זמן עליית ה-EXE: עד שהפייתון מתחיל (נוצרת data\unknown) ועד שהמנועים מוכנים (נוצר data\faces.db).
# שימוש: powershell -File dev\time_exe.ps1 <נתיב ל-EXE או לתיקיית onedir\FaceID.exe>
param([string]$Exe = "C:\Users\יהודה\Desktop\זיהוי פנים\dist\FaceID.exe", [string]$T = "C:\Users\יהודה\AppData\Local\Temp\faceid_time")
Get-Process FaceID -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1
$dir = Split-Path $Exe
if (Test-Path "$dir\data") { Remove-Item -Recurse -Force "$dir\data" }
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath $Exe -PassThru -WorkingDirectory $dir
$py = $null; $ready = $null
while ($sw.Elapsed.TotalSeconds -lt 240 -and -not $ready) {
    if (-not $py -and (Test-Path "$dir\data\unknown")) { $py = $sw.Elapsed.TotalSeconds }
    if (Test-Path "$dir\data\faces.db") { $ready = $sw.Elapsed.TotalSeconds }
    Start-Sleep -Milliseconds 200
}
"python started: {0:N1}s   engines ready: {1:N1}s" -f $py, $ready
Get-Process FaceID -ErrorAction SilentlyContinue | Stop-Process -Force
