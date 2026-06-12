param(
    [int]$Port = 8000,
    [string]$InstallDir = "$env:USERPROFILE\NestCheck",
    [switch]$InstallPython,
    [switch]$CoreOnly,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Require-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Set-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )

    $line = "$Key=$Value"
    $content = Get-Content $Path -Raw
    if ($content -match "(?m)^$([regex]::Escape($Key))=") {
        $content = $content -replace "(?m)^$([regex]::Escape($Key))=.*$", $line
    } else {
        $content = $content.TrimEnd() + "`r`n" + $line + "`r`n"
    }
    Set-Content -Path $Path -Value $content -NoNewline
}

function Invoke-ArchiveDownload {
    param(
        [string]$Uri,
        [string]$OutFile,
        [string]$ManualTargetDir
    )

    $maxAttempts = 3
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            Write-Host "Downloading archive, attempt $attempt of $maxAttempts..."
            if (Require-Command "Start-BitsTransfer") {
                Start-BitsTransfer -Source $Uri -Destination $OutFile -ErrorAction Stop
            } else {
                Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UseBasicParsing -TimeoutSec 600
            }

            $sizeBytes = (Get-Item $OutFile).Length
            if ($sizeBytes -lt 1MB) {
                throw "Downloaded archive is unexpectedly small: $sizeBytes bytes."
            }

            Write-Host ("Downloaded archive size: {0:N1} MB" -f ($sizeBytes / 1MB))
            return
        } catch {
            if ($attempt -ge $maxAttempts) {
                throw "Failed to download NestCheck archive after $maxAttempts attempts. Download $Uri manually, extract it to $ManualTargetDir, then rerun this script from that folder. Last error: $($_.Exception.Message)"
            }

            $delaySeconds = 5 * $attempt
            Write-Warning "Download attempt $attempt failed: $($_.Exception.Message). Retrying in $delaySeconds seconds."
            Start-Sleep -Seconds $delaySeconds
        }
    }
}

function Resolve-RepoRoot {
    param([string]$PreferredInstallDir)

    $scriptRepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..") -ErrorAction SilentlyContinue
    if ($scriptRepoRoot -and (Test-Path (Join-Path $scriptRepoRoot "requirements.txt"))) {
        return $scriptRepoRoot.Path
    }

    if (Test-Path (Join-Path $PreferredInstallDir "requirements.txt")) {
        return (Resolve-Path $PreferredInstallDir).Path
    }

    if (Test-Path $PreferredInstallDir) {
        throw "InstallDir already exists but is not a NestCheck checkout: $PreferredInstallDir"
    }

    Write-Step "Downloading NestCheck from GitHub"
    $archiveUrl = "https://codeload.github.com/TheoEquity/NestCheck/zip/refs/heads/main"
    $stamp = Get-Date -Format "yyyyMMddHHmmss"
    $downloadRoot = Join-Path $env:TEMP "nestcheck-install-$stamp"
    $zipPath = Join-Path $downloadRoot "nestcheck-main.zip"
    $extractRoot = Join-Path $downloadRoot "extract"
    New-Item -ItemType Directory -Path $downloadRoot | Out-Null
    New-Item -ItemType Directory -Path $extractRoot | Out-Null

    Invoke-ArchiveDownload -Uri $archiveUrl -OutFile $zipPath -ManualTargetDir $PreferredInstallDir
    Expand-Archive -Path $zipPath -DestinationPath $extractRoot

    $extracted = Get-ChildItem -Path $extractRoot -Directory | Select-Object -First 1
    if (-not $extracted) {
        throw "Downloaded archive did not contain a project directory."
    }

    $installParent = Split-Path -Parent $PreferredInstallDir
    if (-not (Test-Path $installParent)) {
        New-Item -ItemType Directory -Path $installParent | Out-Null
    }
    Move-Item -Path $extracted.FullName -Destination $PreferredInstallDir
    return (Resolve-Path $PreferredInstallDir).Path
}

function Resolve-PythonCommand {
    if (Require-Command "python") {
        return "python"
    }

    if (-not $InstallPython) {
        throw "Python was not found. Install Python 3.11 first, or rerun with -InstallPython."
    }

    if (-not (Require-Command "winget")) {
        throw "winget was not found. Install Python 3.11 manually from https://www.python.org/downloads/windows/"
    }

    Write-Step "Installing Python 3.11 with winget"
    winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
    throw "Python 3.11 has been installed. Reopen PowerShell, then rerun this script."
}

$RepoRoot = Resolve-RepoRoot -PreferredInstallDir $InstallDir
Set-Location $RepoRoot

Write-Step "Checking Python"
$pythonCommand = Resolve-PythonCommand
try {
    & $pythonCommand --version
} catch {
    throw "Python is not callable from PowerShell. Reopen PowerShell and retry."
}

Write-Step "Preparing virtual environment"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $pythonCommand -m venv .venv
}
$venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

Write-Step "Preparing .env"
$envPath = Join-Path $RepoRoot ".env"
$envExamplePath = Join-Path $RepoRoot ".env.example"
if (-not (Test-Path $envPath)) {
    Copy-Item $envExamplePath $envPath
}
Set-EnvValue -Path $envPath -Key "ADMIN_AUTH_ENABLED" -Value "true"
Set-EnvValue -Path $envPath -Key "API_PORT" -Value $Port
Set-EnvValue -Path $envPath -Key "WEBUI_HOST" -Value "127.0.0.1"

Write-Step "Preparing persistent directories"
foreach ($dir in @("data", "logs", "reports", "strategies")) {
    $path = Join-Path $RepoRoot $dir
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path | Out-Null
    }
}

Write-Step "Installing dependencies"
$env:PYTHONUTF8 = "1"
$null = cmd /c chcp 65001
& $venvPython -m pip install --upgrade pip setuptools wheel
if ($CoreOnly) {
    & $venvPython -m pip install --no-cache-dir python-dotenv pandas fastapi "uvicorn[standard]" litellm tiktoken openai PyYAML
} else {
    & $venvPython -m pip install -r requirements.txt
}

if ($NoStart) {
    Write-Step "Install complete"
    Write-Host "Local URL: http://127.0.0.1:$Port"
    Write-Host "Start command: $venvPython main.py --serve-only --host 127.0.0.1 --port $Port"
    exit 0
}

Write-Step "Starting NestCheck"
Write-Host "Local URL: http://127.0.0.1:$Port"
Write-Host "Press Ctrl + C to stop the service."
& $venvPython main.py --serve-only --host 127.0.0.1 --port $Port
