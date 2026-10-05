<#
  Сборка и установка Android-приложения НарядAI из папки с кириллицей в пути.

  Android Gradle Plugin и компилятор шейдеров Flutter не работают, если в пути
  есть не-латинские символы (например, «Костонай»). Скрипт копирует проект во
  временную папку с латинским путём, собирает там APK и ставит его на
  подключённый телефон или запущенный эмулятор. Исходники остаются на месте.

  Примеры:
    .\build-android.ps1                                   # release для эмулятора
    .\build-android.ps1 -ApiUrl http://192.168.1.50:8000  # для телефона в Wi-Fi
    .\build-android.ps1 -Debug                            # debug-сборка
    .\build-android.ps1 -NoInstall                        # только собрать APK
#>
param(
    [string]$ApiUrl = "http://10.0.2.2:8000",
    [switch]$Debug,
    [switch]$NoInstall
)

$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
$work = Join-Path $env:LOCALAPPDATA "naryad-ai-build\mobile"
$mode = if ($Debug) { "debug" } else { "release" }

if ($work -match '[^\x00-\x7F]') {
    throw "Путь временной папки содержит не-латинские символы: $work. Задайте другую через переменную LOCALAPPDATA."
}

Write-Host "1/3 Копирую проект в $work ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force $work | Out-Null
# /MIR — зеркалирование: удалённые в исходниках файлы удаляются и в копии.
# Сборочные папки не копируем — они у копии свои и переиспользуются между сборками.
robocopy $src $work /MIR /NFL /NDL /NJH /NJS /NP /XD build .dart_tool .gradle .idea | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy завершился с ошибкой $LASTEXITCODE" }

Write-Host "2/3 Собираю APK ($mode, API_URL=$ApiUrl) ..." -ForegroundColor Cyan
Push-Location $work
try {
    flutter pub get | Out-Null
    flutter build apk "--$mode" "--dart-define=API_URL=$ApiUrl"
    if ($LASTEXITCODE -ne 0) { throw "Сборка не удалась (код $LASTEXITCODE)" }
} finally {
    Pop-Location
}

$apk = Join-Path $work "build\app\outputs\flutter-apk\app-$mode.apk"
$out = Join-Path $src "build\naryad-ai-$mode.apk"
New-Item -ItemType Directory -Force (Split-Path $out) | Out-Null
Copy-Item $apk $out -Force
Write-Host "APK: $out" -ForegroundColor Green

if ($NoInstall) { return }

Write-Host "3/3 Устанавливаю на устройство ..." -ForegroundColor Cyan
$adb = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
if (-not (Test-Path $adb)) { $adb = "adb" }
$devices = & $adb devices | Select-String "\tdevice$"
if (-not $devices) {
    Write-Warning "Нет подключённого телефона или эмулятора. Запустите эмулятор (flutter emulators --launch Medium_Phone_API_36.1) и повторите, или поставьте APK вручную."
    return
}
& $adb install -r $apk
& $adb shell monkey -p kz.kostanaymin.naryad_ai -c android.intent.category.LAUNCHER 1 | Out-Null
Write-Host "Готово: приложение установлено и запущено." -ForegroundColor Green
