$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (-not (Get-Command javac -ErrorAction SilentlyContinue)) { throw 'Instala JDK 21 o superior' }
$version = & javac -version 2>&1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ("$version" -notmatch 'javac (\d+)' -or [int]$Matches[1] -lt 21) { throw 'Se requiere JDK 21 o superior' }
New-Item -ItemType Directory -Path "$root/build" -Force | Out-Null
$sources = @(Get-ChildItem -Path "$root/clients-java","$root/frontend-java","$root/server-java","$root/workers/java","$root/benchmarks" -Filter *.java -Recurse | ForEach-Object { $_.FullName })
& javac --release 17 -encoding UTF-8 -cp "$root/lib/*" -d "$root/build" @sources
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'OK: Java compilado en build/'
