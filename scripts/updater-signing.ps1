param(
    [ValidateSet('Initialize','Build','Export','Import')][string]$Mode = 'Build',
    [string]$RecoveryFile,
    [string]$OutputName = 'deletions-0147'
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$signingRoot = Join-Path $repoRoot 'artifacts\signing'
$protectedPath = Join-Path $signingRoot 'updater.key.dpapi'
$configPath = Join-Path $repoRoot 'apps\desktop\src-tauri\tauri.conf.json'
Add-Type -AssemblyName System.Security
function Protect-Key([byte[]]$Bytes) {
    [System.IO.File]::WriteAllBytes($protectedPath, [System.Security.Cryptography.ProtectedData]::Protect(
        $Bytes, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser))
}
function Read-Key {
    return [System.Security.Cryptography.ProtectedData]::Unprotect(
        [System.IO.File]::ReadAllBytes($protectedPath), $null,
        [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
}
function Recovery-Password {
    $secure = Read-Host '恢复密钥密码（至少 12 个字符，请自行保管）' -AsSecureString
    $plain = [System.Net.NetworkCredential]::new('', $secure).Password
    if ($plain.Length -lt 12) { throw 'recovery_password_too_short' }
    return $plain
}
New-Item -ItemType Directory -Force -Path $signingRoot | Out-Null
Push-Location $repoRoot
try {
    if ($Mode -eq 'Initialize') {
        if (Test-Path -LiteralPath $protectedPath) { throw 'signing_key_already_initialized' }
        $temporary = Join-Path $signingRoot 'updater.key'
        if (Test-Path -LiteralPath $temporary) { throw 'temporary_signing_key_exists' }
        try {
            # Never forward CLI output: signer may print the private key.
            $discard = & node node_modules/@tauri-apps/cli/tauri.js signer generate --ci --password= --write-keys $temporary 2>&1
            if ($LASTEXITCODE -ne 0) { throw 'signing_key_generation_failed' }
            $keyBytes = [System.IO.File]::ReadAllBytes($temporary)
            Protect-Key $keyBytes
            $publicKey = [System.IO.File]::ReadAllText($temporary + '.pub').Trim()
            $config = [System.IO.File]::ReadAllText($configPath) | ConvertFrom-Json -AsHashtable
            $config.plugins.updater.pubkey = $publicKey
            [System.IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 30) + "`n", [System.Text.UTF8Encoding]::new($false))
            Write-Output 'signing_key_initialized; private_key_dpapi_current_user; public_key_in_config'
        } finally {
            $discard = $null
            if ($keyBytes) { [Array]::Clear($keyBytes,0,$keyBytes.Length) }
            Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath ($temporary + '.pub') -ErrorAction SilentlyContinue
        }
    } elseif ($Mode -eq 'Build') {
        if (-not (Test-Path -LiteralPath $protectedPath)) { throw 'publisher_signing_key_not_initialized' }
        if (Test-Path Env:TAURI_SIGNING_PRIVATE_KEY) { throw 'signing_environment_already_set' }
        try {
            $keyBytes = Read-Key
            $env:TAURI_SIGNING_PRIVATE_KEY = [System.Text.Encoding]::UTF8.GetString($keyBytes).Trim()
            $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ''
            & .venv\Scripts\python.exe scripts/build-installer.py --build-only --output-name $OutputName
            if ($LASTEXITCODE -ne 0) { throw 'installer_build_failed' }
        } finally {
            Remove-Item Env:TAURI_SIGNING_PRIVATE_KEY -ErrorAction SilentlyContinue
            Remove-Item Env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD -ErrorAction SilentlyContinue
            if ($keyBytes) { [Array]::Clear($keyBytes,0,$keyBytes.Length) }
        }
    } else {
        if (-not $RecoveryFile) { throw 'recovery_file_required' }
        $recoveryPath = [System.IO.Path]::GetFullPath($RecoveryFile)
        if ($Mode -eq 'Export' -and (Test-Path -LiteralPath $recoveryPath)) { throw 'recovery_file_must_be_new' }
        $password = Recovery-Password
        $base64 = [Convert]
        try {
            if ($Mode -eq 'Export') {
                $salt = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
                $nonce = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(12)
                $plainBytes = Read-Key
            } else {
                if (Test-Path -LiteralPath $protectedPath) { throw 'signing_key_already_initialized' }
                $record = [System.IO.File]::ReadAllText($recoveryPath) | ConvertFrom-Json
                if ($record.format -ne 'dreamtalk-updater-key-v1' -or $record.iterations -ne 600000) { throw 'recovery_format_invalid' }
                $salt = $base64::FromBase64String($record.salt)
                $nonce = $base64::FromBase64String($record.nonce)
                $config = [System.IO.File]::ReadAllText($configPath) | ConvertFrom-Json
                if ($record.pubkey -ne $config.plugins.updater.pubkey) { throw 'recovery_public_key_mismatch' }
            }
            $derived = [System.Security.Cryptography.Rfc2898DeriveBytes]::Pbkdf2($password,$salt,600000,[System.Security.Cryptography.HashAlgorithmName]::SHA256,32)
            $aes = [System.Security.Cryptography.AesGcm]::new($derived,16)
            if ($Mode -eq 'Export') {
                $cipher = [byte[]]::new($plainBytes.Length)
                $tag = [byte[]]::new(16)
                $aes.Encrypt($nonce,$plainBytes,$cipher,$tag)
                $config = [System.IO.File]::ReadAllText($configPath) | ConvertFrom-Json
                $record = @{ format='dreamtalk-updater-key-v1'; iterations=600000; pubkey=$config.plugins.updater.pubkey; salt=$base64::ToBase64String($salt); nonce=$base64::ToBase64String($nonce); cipher=$base64::ToBase64String($cipher); tag=$base64::ToBase64String($tag) }
                [System.IO.File]::WriteAllText($recoveryPath,($record | ConvertTo-Json),[System.Text.UTF8Encoding]::new($false))
                Write-Output 'encrypted_recovery_key_exported'
            } else {
                $cipher = $base64::FromBase64String($record.cipher)
                $plainBytes = [byte[]]::new($cipher.Length)
                $aes.Decrypt($nonce,$cipher,$base64::FromBase64String($record.tag),$plainBytes)
                Protect-Key $plainBytes
                Write-Output 'signing_key_restored_for_current_user'
            }
        } finally {
            $password = $null
            if ($aes) { $aes.Dispose() }
            if ($derived) { [Array]::Clear($derived,0,$derived.Length) }
            if ($plainBytes) { [Array]::Clear($plainBytes,0,$plainBytes.Length) }
        }
    }
} finally { Pop-Location }
