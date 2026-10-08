<#
  НарядAI — запуск одной командой (Windows).
  Двойной клик по start.bat или: powershell -ExecutionPolicy Bypass -File start.ps1

  Что делает:
    1. Проверяет Docker (запускает Docker Desktop, если он установлен, но выключен).
    2. Подбирает свободные порты: веб-панель 8080, API 8000, PostgreSQL 5432 — или следующие свободные.
    3. Собирает и запускает контейнеры, ждёт готовности API и панели.
    4. Загружает демо-данные (пользователи, справочники) — повторный запуск их не трогает.
    5. Печатает адреса и логины и открывает панель в браузере.

  Параметры:
    -NoDemo   не загружать демо-данные (панель покажет экран первичной настройки)
    -NoOpen   не открывать браузер
    -Stop     остановить контейнеры (данные сохраняются)
#>
param(
    [switch]$NoDemo,
    [switch]$NoOpen,
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "`nОШИБКА: $text" -ForegroundColor Red; exit 1 }

# docker пишет прогресс в stderr — в PowerShell 5.1 это не должно считаться ошибкой
function Invoke-Docker {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { & docker @args 2>&1 | ForEach-Object { "$_" } } finally { $ErrorActionPreference = $old }
}

# ---------- 1. Docker ----------
Step 'Проверяю Docker'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $bin = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin'
    if (Test-Path (Join-Path $bin 'docker.exe')) { $env:Path = "$bin;$env:Path" }
    else { Fail 'Docker не найден. Установите Docker Desktop: https://www.docker.com/products/docker-desktop/' }
}

$null = Invoke-Docker info
if ($LASTEXITCODE -ne 0) {
    $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path $desktop)) { Fail 'Docker не запущен. Запустите Docker и повторите.' }
    Write-Host 'Docker Desktop не запущен — запускаю (до 3 минут)...'
    Start-Process $desktop
    $deadline = (Get-Date).AddMinutes(3)
    do { Start-Sleep 3; $null = Invoke-Docker info } while ($LASTEXITCODE -ne 0 -and (Get-Date) -lt $deadline)
    if ($LASTEXITCODE -ne 0) { Fail 'Docker Desktop не запустился за 3 минуты. Откройте его вручную и повторите.' }
}

$composeVer = (Invoke-Docker compose version --short | Select-Object -Last 1) -replace '^v', ''
if ($LASTEXITCODE -ne 0) { Fail 'Нужен Docker Compose v2 (команда "docker compose").' }
try { $v = [version](($composeVer -split '[-+]')[0]) } catch { $v = [version]'0.0' }
if ($v -lt [version]'2.24') { Fail "Нужен Docker Compose 2.24 или новее, установлен $composeVer. Обновите Docker Desktop." }
Write-Host "Docker Compose $composeVer"

if ($Stop) {
    Step 'Останавливаю контейнеры'
    Invoke-Docker compose stop | Write-Host
    Write-Host 'Остановлено. Данные сохранены, запуск снова — start.bat' -ForegroundColor Green
    exit 0
}

# ---------- 2. Порты ----------
Step 'Подбираю свободные порты'
# свои контейнеры от прошлого запуска освобождают порты, чтобы их можно было занять снова
$null = Invoke-Docker compose stop

function Get-DotEnv($name) {
    if (-not (Test-Path '.env')) { return $null }
    $line = Get-Content '.env' | Where-Object { $_ -match "^\s*$name\s*=" } | Select-Object -Last 1
    if ($line) { return ($line -split '=', 2)[1].Trim() } else { return $null }
}

function Test-PortFree([int]$port) {
    foreach ($addr in [Net.IPAddress]::Loopback, [Net.IPAddress]::Any) {
        $listener = New-Object Net.Sockets.TcpListener($addr, $port)
        try { $listener.Start() } catch { return $false } finally { try { $listener.Stop() } catch { } }
    }
    return $true
}

function Select-Port($name, [int]$default) {
    $preferred = [Environment]::GetEnvironmentVariable($name)
    if (-not $preferred) { $preferred = Get-DotEnv $name }
    if (-not $preferred) { $preferred = $default }
    for ($p = [int]$preferred; $p -lt [int]$preferred + 200; $p++) {
        if (Test-PortFree $p) {
            if ($p -ne [int]$preferred) { Write-Host "  порт $preferred занят — $name=$p" -ForegroundColor Yellow }
            [Environment]::SetEnvironmentVariable($name, "$p")
            return $p
        }
    }
    Fail "Не нашёл свободный порт для $name рядом с $preferred"
}

$webPort = Select-Port 'WEB_PORT' 8080
$apiPort = Select-Port 'API_PORT' 8000
$dbPort  = Select-Port 'DB_PORT' 5432
Write-Host "  панель :$webPort   API :$apiPort   PostgreSQL :$dbPort"

# IP компьютера в локальной сети — панель покажет его в «Настройки → Подключение мобильного приложения»
$lanIps = @(Get-NetIPConfiguration -ErrorAction SilentlyContinue |
    Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
    ForEach-Object { $_.IPv4Address.IPAddress } | Select-Object -Unique)
$env:SERVER_LAN_IPS = $lanIps -join ','
$lan = $lanIps | Select-Object -First 1

# ---------- 3. Сборка и запуск ----------
Step 'Собираю и запускаю контейнеры (первый раз — несколько минут)'
Invoke-Docker compose up -d --build | Where-Object { $_ -match 'Built|Started|Running|Healthy|error|Error|failed' } | Write-Host
if ($LASTEXITCODE -ne 0) { Fail 'docker compose up завершился с ошибкой — подробности выше.' }

Step 'Жду готовности API и панели'
$deadline = (Get-Date).AddMinutes(3)
$ready = $false
do {
    try {
        $null = Invoke-WebRequest "http://localhost:$apiPort/health" -UseBasicParsing -TimeoutSec 3
        $null = Invoke-WebRequest "http://localhost:$webPort/api/v1/setup/status" -UseBasicParsing -TimeoutSec 3
        $ready = $true
    } catch { Start-Sleep 2 }
} while (-not $ready -and (Get-Date) -lt $deadline)
if (-not $ready) {
    Invoke-Docker compose logs --tail 40 api | Write-Host
    Fail 'API не ответил за 3 минуты — логи выше.'
}

# ---------- 4. Демо-данные ----------
if (-not $NoDemo) {
    Step 'Загружаю демо-данные'
    Invoke-Docker compose exec -T api python -m app.seed | Write-Host
    if ($LASTEXITCODE -ne 0) { Fail 'Не удалось загрузить демо-данные.' }
}

# ---------- 5. Итог ----------
Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host ' НарядAI запущен' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host " Веб-панель:   http://localhost:$webPort"
if ($lan) { Write-Host " Из сети:      http://${lan}:$webPort" }
Write-Host " Swagger API:  http://localhost:$apiPort/docs"
if (-not $NoDemo) {
    Write-Host ''
    Write-Host ' Демо-вход (backend/app/seed.py, только для демонстрации):'
    Write-Host '   веб-панель:  admin / Admin#2026     master1 / Master#2026     boss / Boss#2026'
    Write-Host '   приложение:  исполнители 1001-1004, ПИН 2580 (или пароль Worker#2026)'
} else {
    Write-Host ''
    Write-Host ' Откройте панель — она предложит создать первого администратора.'
}
Write-Host ''
if ($lan) {
    $phoneAddr = if ($webPort -eq 8080) { $lan } else { "${lan}:$webPort" }
    Write-Host " Мобильное приложение: на экране входа «Сервер → Изменить» введите $phoneAddr"
    Write-Host '   (эмулятор Android на этом компьютере — ничего вводить не нужно)'
}
Write-Host ' Остановить: start.bat -Stop   (данные сохраняются)'
Write-Host '============================================================' -ForegroundColor Green

if (-not $NoOpen) { Start-Process "http://localhost:$webPort" }
