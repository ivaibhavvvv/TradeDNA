$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path -Path $DesktopPath -ChildPath "TradeDNA.lnk"

$TargetPath = "C:\Users\vaibh\.gemini\antigravity-ide\scratch\tradedna\start_tradedna.bat"
$WorkingDirectory = "C:\Users\vaibh\.gemini\antigravity-ide\scratch\tradedna"

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = $WorkingDirectory
$Shortcut.Description = "TradeDNA Exness MT5 Intelligence Platform"
$Shortcut.Save()

Write-Host "TradeDNA desktop shortcut created successfully at: $ShortcutPath" -ForegroundColor Green
