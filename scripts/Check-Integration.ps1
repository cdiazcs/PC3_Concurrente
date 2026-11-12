param([switch]$Tcp, [switch]$Rabbit, [switch]$Services, [switch]$Phase2, [switch]$Android, [ValidateSet('all','1','2','3')][string]$Member = 'all')
$ErrorActionPreference = 'Stop'
$python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
$arguments = @("$PSScriptRoot/check_integration.py", '--member', $Member)
if ($Tcp) { $arguments += '--tcp' }
if ($Rabbit) { $arguments += '--rabbit' }
if ($Services) { $arguments += '--services' }
if ($Phase2) { $arguments += '--phase2' }
if ($Android) { $arguments += '--android' }
& $python @arguments
exit $LASTEXITCODE
