$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$venvPython = Join-Path $backendRoot ".venv\Scripts\python.exe"
$logsRoot = Join-Path $projectRoot "logs"

# Tải file model lớn bằng HTTP thông thường trên Windows; tránh Xet giữ toàn bộ chunk trong bộ nhớ.
$env:HF_HUB_DISABLE_XET = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$env:HF_HUB_DOWNLOAD_TIMEOUT = "300"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Test-Url([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

function Wait-Url([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Url $Url) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

Set-Location $projectRoot

Write-Step "Kiem tra cong cu"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw "Khong tim thay Python. Can Python 3.11 tro len." }
$pythonVersion = & $python.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$pythonParts = $pythonVersion.Split(".")
if ([int]$pythonParts[0] -lt 3 -or ([int]$pythonParts[0] -eq 3 -and [int]$pythonParts[1] -lt 11)) {
    throw "Python $pythonVersion qua cu. Can Python 3.11 tro len."
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Khong tim thay Node.js. Can Node 20 tro len." }
$nodeMajor = [int]((& node --version).TrimStart("v").Split(".")[0])
if ($nodeMajor -lt 20) { throw "Node.js qua cu. Can Node 20 tro len." }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw "Khong tim thay npm." }

Write-Step "Chuan bi backend"
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $python.Source -m venv (Join-Path $backendRoot ".venv")
}
& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $backendRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Khong cai duoc dependency backend." }

Write-Step "Chuan bi frontend"
& npm.cmd install
if ($LASTEXITCODE -ne 0) { throw "Khong cai duoc dependency frontend." }

New-Item -ItemType Directory -Path $logsRoot -Force | Out-Null

Write-Step "Khoi dong backend"
if (-not (Test-Url "http://127.0.0.1:8000/api/health")) {
    $backendProcess = Start-Process -FilePath $venvPython `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--port", "8000") `
        -WorkingDirectory $backendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logsRoot "backend.out.log") `
        -RedirectStandardError (Join-Path $logsRoot "backend.err.log") `
        -PassThru
    Set-Content -LiteralPath (Join-Path $logsRoot "backend.pid") -Value $backendProcess.Id
}
if (-not (Wait-Url "http://127.0.0.1:8000/api/health" 60)) {
    throw "Backend khong san sang. Xem logs\backend.err.log."
}

Write-Step "Khoi dong frontend"
if (-not (Test-Url "http://127.0.0.1:3000")) {
    $frontendProcess = Start-Process -FilePath "npm.cmd" `
        -ArgumentList @("run", "dev") `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logsRoot "frontend.out.log") `
        -RedirectStandardError (Join-Path $logsRoot "frontend.err.log") `
        -PassThru
    Set-Content -LiteralPath (Join-Path $logsRoot "frontend.pid") -Value $frontendProcess.Id
}
if (-not (Wait-Url "http://127.0.0.1:3000" 60)) {
    throw "Frontend khong san sang. Xem logs\frontend.err.log."
}

Write-Host "`nDa chay xong:" -ForegroundColor Green
Write-Host "  App:      http://localhost:3000"
Write-Host "  API docs: http://localhost:8000/docs"
Write-Host "  Dang nhap: bs.an / demo"
Start-Process "http://localhost:3000"
