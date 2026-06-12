param(
    [int]$Port = 8000,
    [string]$InstallDir = "$env:USERPROFILE\NestCheck",
    [switch]$InstallDocker,
    [switch]$SkipFirewallRule
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
    if ($scriptRepoRoot -and (Test-Path (Join-Path $scriptRepoRoot "docker\docker-compose.yml"))) {
        return $scriptRepoRoot.Path
    }

    if (Test-Path (Join-Path $PreferredInstallDir "docker\docker-compose.yml")) {
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

$RepoRoot = Resolve-RepoRoot -PreferredInstallDir $InstallDir
Set-Location $RepoRoot

Write-Step "Checking Docker"
$dockerAvailable = Require-Command "docker"
if (-not $dockerAvailable) {
    if (-not $InstallDocker) {
        throw "Docker was not found. Install Docker Desktop first, or rerun with -InstallDocker."
    }

    if (-not (Require-Command "winget")) {
        throw "winget was not found. Install Docker Desktop manually from https://www.docker.com/products/docker-desktop/"
    }

    Write-Step "Installing Docker Desktop with winget"
    winget install --id Docker.DockerDesktop -e --accept-package-agreements --accept-source-agreements
    throw "Docker Desktop has been installed. Start Docker Desktop once, wait until it is running, then rerun this script."
}

try {
    docker info | Out-Null
} catch {
    throw "Docker Desktop is installed but not running. Start Docker Desktop, wait until it is ready, then rerun this script."
}

Write-Step "Preparing .env"
$envPath = Join-Path $RepoRoot ".env"
$envExamplePath = Join-Path $RepoRoot ".env.example"
if (-not (Test-Path $envPath)) {
    Copy-Item $envExamplePath $envPath
}
Set-EnvValue -Path $envPath -Key "ADMIN_AUTH_ENABLED" -Value "true"
Set-EnvValue -Path $envPath -Key "API_PORT" -Value $Port
Set-EnvValue -Path $envPath -Key "WEBUI_HOST" -Value "0.0.0.0"

Write-Step "Preparing persistent directories"
foreach ($dir in @("data", "logs", "reports", "strategies")) {
    $path = Join-Path $RepoRoot $dir
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path | Out-Null
    }
}

if (-not $SkipFirewallRule) {
    Write-Step "Configuring Windows Firewall"
    try {
        $ruleName = "NestCheck Tailscale $Port"
        $existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
        if (-not $existingRule) {
            New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private | Out-Null
        }
    } catch {
        Write-Warning "Failed to create firewall rule automatically. Run PowerShell as Administrator or allow Docker/Python when Windows prompts."
    }
}

Write-Step "Starting NestCheck with Docker Compose"
docker compose -f docker/docker-compose.yml up -d --build server

Write-Step "Deployment complete"
$tailscaleIp = $null
if (Require-Command "tailscale") {
    try {
        $tailscaleIp = (tailscale ip -4 | Select-Object -First 1).Trim()
    } catch {
        $tailscaleIp = $null
    }
}

Write-Host "Local URL: http://127.0.0.1:$Port"
if ($tailscaleIp) {
    Write-Host "Tailscale URL: http://$tailscaleIp`:$Port"
} else {
    Write-Host "Tailscale URL: run 'tailscale ip -4' and open http://<tailscale-ip>:$Port"
}
Write-Host "Data directory: $RepoRoot\data"
Write-Host "Logs directory: $RepoRoot\logs"
Write-Host "Reports directory: $RepoRoot\reports"
