$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Path build -Force | Out-Null
$java = @(Get-ChildItem -Path clients-java,frontend-java,server-java,workers/java -Filter *.java -Recurse | ForEach-Object { $_.FullName })
& javac -encoding UTF-8 -d build @java
if ($LASTEXITCODE -ne 0) { throw "No se pudo compilar Java" }
Write-Host "Java compilado en build/"
