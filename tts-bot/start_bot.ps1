# AI Ovoz Bot — ishga tushirish skripti
# Agar bot allaqali ishlayotgan bo'lsa, yangisini ishga tushirmaydi
# (TelegramConflictError oldini oladi).

$ErrorActionPreference = "SilentlyContinue"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $dir "venv731\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Output "Python topilmadi: $py"
    exit 1
}

# 1) Allaqali ishlayotgan nusxa bormi?
$running = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "bot\.py" } |
    Select-Object -ExpandProperty ProcessId

if ($running) {
    Write-Output "Bot allaqali ishlayapti (PID: $($running -join ', ')). Yangi nusxa ishga tushirilmaydi."
    exit 0
}

# 2) Eski nusxalarni tozalash (agar qolsa)
$stale = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "bot\.py" }
foreach ($p in $stale) { Stop-Process -Id $p.ProcessId -Force }

# 3) Ishga tushirish
$log = Join-Path $dir "bot_startup.log"
Write-Output ("[{0}] Bot ishga tushirilmoqda..." -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
Start-Process -FilePath $py -ArgumentList "bot.py" -WorkingDirectory $dir `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err" -WindowStyle Hidden
Start-Sleep -Seconds 4

# 4) Tekshirish
$now = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "bot\.py" } |
    Select-Object -ExpandProperty ProcessId
if ($now) {
    Write-Output "Bot ishga tushdi (PID: $($now -join ', '))"
} else {
    Write-Output "Bot ishga tushmadi! Log: $log.err"
    Get-Content "$log.err" -Tail 15
}
