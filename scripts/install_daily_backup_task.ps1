param(
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$Time = '22:00'
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente Python do aplicativo não encontrado: $python. Execute start.bat setup primeiro."
}

$taskName = 'Agatha Studio - Backup Externo'
$action = New-ScheduledTaskAction -Execute $python `
    -Argument '-m flask --app wsgi backup-offsite' `
    -WorkingDirectory $project
$trigger = New-ScheduledTaskTrigger -Daily -At ([TimeSpan]::ParseExact($Time, 'hh\:mm', $null))
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Description `
    'Envia diariamente o banco e os uploads do Agatha Studio para o destino Restic cifrado.' -Force | Out-Null
Write-Output "Tarefa '$taskName' criada para $Time. Ela roda na sessão deste usuário; se o PC estiver desligado, tenta ao próximo login."
