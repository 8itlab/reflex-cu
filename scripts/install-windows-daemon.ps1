# Sets up and (re)starts the reflexcu daemon in the interactive desktop session of this Windows machine.
# Run it from the directory that contains the reflexcu\ package (a clone of the repo, or a copy of it).
#
#   powershell -ExecutionPolicy Bypass -File scripts\install-windows-daemon.ps1            install / restart
#   powershell -ExecutionPolicy Bypass -File scripts\install-windows-daemon.ps1 -Stop      stop and disable
#
# -Port      daemon port on 127.0.0.1 (default 8765)
# -PipIndex  alternative package index, e.g. https://pypi.tuna.tsinghua.edu.cn/simple
param([switch]$Stop, [int]$Port = 8765, [string]$PipIndex = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$task = 'reflexcu-daemon'
$py = Join-Path $root 'venv\Scripts\python.exe'
$pyw = Join-Path $root 'venv\Scripts\pythonw.exe'

Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -like '*reflexcu*daemon.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
if ($Stop) { Disable-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue | Out-Null; 'stopped'; exit }

if (-not (Test-Path $py)) {
    python -m venv (Join-Path $root 'venv')
    $pip = @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', '-r', (Join-Path $root 'requirements-windows.txt'))
    if ($PipIndex) { $pip += @('-i', $PipIndex) }
    & $py @pip
}

$daemon = Join-Path $root 'reflexcu\daemon.py'
$a = New-ScheduledTaskAction -Execute $pyw -Argument "`"$daemon`"" -WorkingDirectory $root
$t = New-ScheduledTaskTrigger -AtLogOn -User "$env:COMPUTERNAME\$env:USERNAME"
# Interactive: the daemon must live in the desktop session to see the screen and send input.
# Highest: without it, input does not reach windows of elevated programs.
$p = New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\$env:USERNAME" -LogonType Interactive -RunLevel Highest
$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
if ($Port -ne 8765) { [Environment]::SetEnvironmentVariable('CU_PORT', "$Port", 'User') }
Register-ScheduledTask -TaskName $task -Action $a -Trigger $t -Principal $p -Settings $s -Force | Out-Null
Start-ScheduledTask -TaskName $task
Start-Sleep -Seconds 4
$up = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($up) { "reflexcu daemon listening on 127.0.0.1:$Port (token: $root\token.txt)" }
else { 'NOT listening'; Get-Content (Join-Path $root 'daemon.log') -Tail 20 -ErrorAction SilentlyContinue }
