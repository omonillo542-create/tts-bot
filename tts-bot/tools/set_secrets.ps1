# GitHub Actions secrets ni shifrlab qo'yish (sealed box orqali)
$ErrorActionPreference = "Stop"
$repo = $args[0]
if (-not $repo) { Write-Output "Usage: set_secrets.ps1 <repo>"; exit 1 }

$dir = "C:\Users\omonillo\Documents\Default Project\tts-bot"
$tmp = "C:\Users\omonillo\AppData\Local\Temp\opencode"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

# GitHub PAT
$cred = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
$pass = ($cred | Where-Object { $_ -match "^password=" }) -replace "^password=", ""
$h = @{ Authorization = "Bearer $pass"; Accept = "application/vnd.github+json"; "X-GitHub-Api-Version" = "2022-11-28" }

# Repo public key
$pk = Invoke-RestMethod -Uri "https://api.github.com/repos/omonillo542-create/$repo/actions/secrets/public-key" -Headers $h -Method Get
Write-Output ("public-key_id: " + $pk.key_id)

# .env dan qiymatlar
$envMap = @{}
Get-Content (Join-Path $dir ".env") | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $k, $v = $_.Split('=', 2)
    $envMap[$k.Trim()] = $v.Trim()
}

$secrets = @{
    "BOT_TOKEN"             = $envMap["BOT_TOKEN"]
    "MIYYA_API_KEY"         = $envMap["MIYYA_API_KEY"]
    "OPENROUTER_API_KEY"    = $envMap["OPENROUTER_API_KEY"]
    "OPENROUTER_THINKING_KEY" = $envMap["OPENROUTER_THINKING_KEY"]
    "HF_TOKEN"              = $envMap["HF_TOKEN"]
}

foreach ($name in $secrets.Keys) {
    $val = $secrets[$name]
    if (-not $val) { Write-Output ("  $name : qiymat yo'q, o'tkizildi"); continue }
    $pf = Join-Path $tmp "plain_$name.txt"
    $of = Join-Path $tmp "sealed_$name.txt"
    [System.IO.File]::WriteAllText($pf, $val, (New-Object System.Text.UTF8Encoding $false))
    $r = & node (Join-Path $dir "tools\seal.js") $pk.key $pf $of 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Output ("  $name : shifrlash xatosi - $r"); continue }
    $enc = (Get-Content $of -Raw).Trim()
    $body = @{ encrypted_value = $enc; key_id = $pk.key_id } | ConvertTo-Json -Compress
    try {
        Invoke-RestMethod -Uri "https://api.github.com/repos/omonillo542-create/$repo/actions/secrets/$name" -Headers $h -Method Put -Body $body -ContentType "application/json" | Out-Null
        Write-Output ("  $name : вњ… qo'yildi")
    } catch {
        Write-Output ("  $name : вќЊ " + $_.Exception.Message)
    }
    Remove-Item $pf, $of -Force -ErrorAction SilentlyContinue
}

# Tekshirish
$list = Invoke-RestMethod -Uri "https://api.github.com/repos/omonillo542-create/$repo/actions/secrets" -Headers $h -Method Get
Write-Output ("Mavjud secretlar: " + (($list.secrets | ForEach-Object { $_.name }) -join ", "))

