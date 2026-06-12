param(
    [int]$Port = 8000,
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

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
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
