# Installer-owned opaque backup, before any old uninstaller or program replacement.
# Never opens SQLite, prints credentials, changes startup, or kills processes.
param([string]$Version = '')
$ErrorActionPreference = 'Stop'
$identity = 'app.livingworld.desktop'
$live = Join-Path $env:APPDATA $identity
$root = Join-Path $env:LOCALAPPDATA 'dreamtalk-backups'
$script:copiedFiles = 0
$script:copiedBytes = [long]0
function AssertPlain([string]$path) {
    if (-not [IO.Path]::IsPathRooted($path)) { throw 'save_path_invalid' }
    $item = $path
    while ($item) {
        if (Test-Path -LiteralPath $item) {
            if ((Get-Item -LiteralPath $item -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'save_link_rejected' }
        }
        $parent = [IO.Path]::GetDirectoryName($item)
        if ($parent -eq $item) { break }
        $item = $parent
    }
}
function CopyTree([string]$source, [string]$target) {
    AssertPlain $source
    New-Item -ItemType Directory -Path $target | Out-Null
    foreach ($entry in @(Get-ChildItem -LiteralPath $source -Force)) {
        AssertPlain $entry.FullName
        if ($entry.Name -eq 'cache') { continue }
        $destination = Join-Path $target $entry.Name
        if ($entry.PSIsContainer) { CopyTree $entry.FullName $destination }
        else {
            $script:copiedFiles += 1
            $script:copiedBytes += $entry.Length
            if ($script:copiedFiles -gt 100000 -or $script:copiedBytes -gt 34359738368) { throw 'save_backup_too_large' }
            [IO.File]::Copy($entry.FullName, $destination, $false)
        }
    }
}
try {
    AssertPlain $live
    AssertPlain $root
    if (-not (Test-Path -LiteralPath (Join-Path $live 'data/runtime.sqlite3'))) { Write-Output 'no_existing_save'; exit 0 }
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $running = @(Get-CimInstance Win32_Process | Where-Object {
            $_.Name -in @('dreamtalk-desktop.exe','dreamtalk-core.exe') -or
            ($_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -and $_.CommandLine.Contains('--bootstrap-path') -and $_.CommandLine.IndexOf($live,[StringComparison]::OrdinalIgnoreCase) -ge 0)
        })
        if ($running.Count -eq 0) { break }
        if ([DateTime]::UtcNow -ge $deadline) { throw 'save_application_still_running' }
        Start-Sleep -Milliseconds 250
    } while ($true)
    $id = [Guid]::NewGuid().ToString()
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    $ownerFile = Join-Path $root '.dreamtalk-backup-root.json'
    if ((Test-Path -LiteralPath $ownerFile) -and (Get-Content -LiteralPath $ownerFile -Raw | ConvertFrom-Json).identity -ne $identity) { throw 'save_backup_location_invalid' }
    @{identity=$identity} | ConvertTo-Json | Set-Content -LiteralPath $ownerFile -Encoding UTF8
    $folder = Join-Path (Join-Path $root 'snapshots') $id
    $payload = Join-Path $folder 'payload'
    New-Item -ItemType Directory -Path $payload | Out-Null
    CopyTree (Join-Path $live 'data') (Join-Path $payload 'data')
    if (Test-Path -LiteralPath (Join-Path $live 'config')) { CopyTree (Join-Path $live 'config') (Join-Path $payload 'config') }
    $marker = '.dreamtalk-storage.json'
    $storage = [Guid]::NewGuid().ToString()
    if (Test-Path -LiteralPath (Join-Path $live $marker)) {
        [IO.File]::Copy((Join-Path $live $marker),(Join-Path $payload $marker),$false)
        $existing = Get-Content -LiteralPath (Join-Path $live $marker) -Raw | ConvertFrom-Json
        if ($existing.identity -ne $identity) { throw 'save_storage_identity_invalid' }
        $storage = ([Guid]$existing.storage_id).ToString()
    } else {
        @{identity=$identity;storage_id=$storage} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $payload $marker) -Encoding UTF8
    }
    $files = [ordered]@{}
    foreach ($file in @(Get-ChildItem -LiteralPath $payload -Recurse -File -Force)) {
        AssertPlain $file.FullName
        $relative = $file.FullName.Substring($payload.Length + 1).Replace('\','/')
        $files[$relative] = @{bytes=$file.Length;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
        if ($relative -ne $marker) {
            $original = Join-Path $live $relative
            if ((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant() -ne $files[$relative].sha256) { throw 'save_changed_during_backup' }
        }
    }
    @{identity=$identity;format=1;id=$id;storage_id=$storage;created_at=[DateTime]::UtcNow.ToString('o');version=$Version;reason='pre_install';info=$null;files=$files;complete=$true} |
        ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $folder 'snapshot.json') -Encoding UTF8
    Write-Output 'save_preinstall_backup_created'
} catch { Write-Output 'save_preinstall_backup_failed'; exit 1 }
