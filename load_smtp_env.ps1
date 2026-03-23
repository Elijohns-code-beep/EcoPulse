param(
    [string]$EnvFile = ".\smtp.env"
)

if (-not (Test-Path $EnvFile)) {
    Write-Error "Env file not found: $EnvFile"
    exit 1
}

function Parse-EnvLine {
    param([string]$Line)

    $trimmed = $Line.Trim()
    if ($trimmed.Length -eq 0) { return $null }
    if ($trimmed.StartsWith("#")) { return $null }

    # Match: KEY=VALUE (KEY allows letters/numbers/_; VALUE may contain anything after '=')
    $m = [regex]::Match($trimmed, '^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$')
    if (-not $m.Success) { return $null }

    $key = $m.Groups[1].Value
    $valRaw = $m.Groups[2].Value.Trim()

    # Strip optional surrounding quotes
    if ($valRaw.StartsWith('"') -and $valRaw.EndsWith('"') -and $valRaw.Length -ge 2) {
        $valRaw = $valRaw.Substring(1, $valRaw.Length - 2)
    }
    if ($valRaw.StartsWith("'") -and $valRaw.EndsWith("'") -and $valRaw.Length -ge 2) {
        $valRaw = $valRaw.Substring(1, $valRaw.Length - 2)
    }

    return [pscustomobject]@{ Key = $key; Value = $valRaw }
}

$lines = Get-Content $EnvFile

$setCount = 0
$skipCount = 0
$warnCount = 0

foreach ($line in $lines) {
    $parsed = Parse-EnvLine -Line $line
    if ($null -eq $parsed) { continue }

    $key = $parsed.Key
    $val = $parsed.Value

    # Gmail app passwords are commonly displayed with spaces.
    # SMTP login expects the raw password characters, so strip whitespace.
    if ($key -eq 'ECOULSE_SMTP_PASSWORD') {
        # Remove all whitespace + any other separators, leaving only the raw password characters.
        $val = ($val -replace '\s+', '')
        $val = ($val -replace '[^0-9A-Za-z]', '')
        if ($val.Length -ne 16) {
            Write-Warning "ECOULSE_SMTP_PASSWORD sanitized length is $($val.Length). Gmail App Passwords are usually 16 characters."
        }
    }

    # Only set if env var is missing or empty.
    # PowerShell doesn't allow $env:$key dynamic access directly, so we read the env var via Get-Item.
    $existingItem = Get-Item -Path "Env:$key" -ErrorAction SilentlyContinue
    $existing = if ($null -eq $existingItem) { "" } else { [string]$existingItem.Value }
    if (-not [string]::IsNullOrWhiteSpace($existing)) {
        $skipCount++
        Write-Host "Skipping (already set): $key"
        continue
    }

    if ([string]::IsNullOrWhiteSpace($val)) {
        $warnCount++
        Write-Warning "Value is empty in $EnvFile for: $key (skipping set)"
        continue
    }

    # Set in current PowerShell session
    Set-Item -Path "env:$key" -Value $val
    $setCount++
    Write-Host "Set: $key"
}

Write-Host "Done. Set=$setCount Skip=$skipCount Warnings=$warnCount"

