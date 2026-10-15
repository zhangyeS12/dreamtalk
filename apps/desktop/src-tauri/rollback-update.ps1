# Desktop-owned recovery for an upgrade which has not admitted business work.
param([Parameter(Mandatory=$true)][string]$RequestPath)
$ErrorActionPreference = 'Stop'
$request = Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json
function Plain([string]$path) {
    if (-not [IO.Path]::IsPathRooted($path)) { throw 'rollback_path_invalid' }
    $part = $path
    while ($part) {
        if ((Test-Path -LiteralPath $part) -and ((Get-Item -LiteralPath $part -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'rollback_link_rejected' }
        $next = [IO.Path]::GetDirectoryName($part)
        if ($next -eq $part) { break }
        $part = $next
    }
    return [IO.Path]::GetFullPath($path)
}
function Owned([string]$root, [string]$relative) {
    if (-not $relative -or $relative.Contains(':') -or [IO.Path]::IsPathRooted($relative) -or $relative.Split([char[]]@('/','\')) -contains '..') { throw 'rollback_inventory_invalid' }
    $path = Plain (Join-Path $root $relative)
    if (-not $path.StartsWith((Plain $root).TrimEnd('\') + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'rollback_inventory_invalid' }
    return $path
}
function CopyTree([string]$source,[string]$target) {
    Plain $source | Out-Null
    if (Test-Path -LiteralPath $target) { throw 'rollback_target_exists' }
    New-Item -ItemType Directory -Path $target | Out-Null
    foreach ($entry in @(Get-ChildItem -LiteralPath $source -Force)) {
        Plain $entry.FullName | Out-Null
        $destination = Join-Path $target $entry.Name
        if ($entry.PSIsContainer) { CopyTree $entry.FullName $destination }
        else { [IO.File]::Copy($entry.FullName,$destination,$false) }
    }
}
$live = Plain $request.app_data
$program = Plain $request.program_root
$recovery = Plain $request.recovery
$result = @{status='failed';private_files_preserved=$true}
try {
    if ([IO.Path]::GetFileName($live) -ne 'app.livingworld.desktop' -or (Test-Path -LiteralPath (Join-Path $program '.git'))) { throw 'rollback_path_invalid' }
    $expectedRecovery = Plain (Join-Path $live 'updates/recovery')
    if ([IO.Path]::GetDirectoryName($recovery) -ne $expectedRecovery) { throw 'rollback_path_invalid' }
    [Guid]::Parse([IO.Path]::GetFileName($recovery)) | Out-Null
    $handoff = Get-Content -LiteralPath (Join-Path $live 'updates/handoff.json') -Raw | ConvertFrom-Json
    if ($handoff.identity -ne 'app.livingworld.desktop' -or $handoff.recovery -ne $recovery -or -not $handoff.old_package) { throw 'rollback_handoff_invalid' }
    $verified = Join-Path $live 'updates/verified.json'
    if ((Test-Path -LiteralPath $verified) -and (Get-Content -LiteralPath $verified -Raw | ConvertFrom-Json).recovery -eq $recovery) { throw 'rollback_new_data_may_exist' }
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        $running = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('dreamtalk-desktop.exe','dreamtalk-core.exe') })
        if ($running.Count -eq 0) { break }
        if ([DateTime]::UtcNow -ge $deadline) { throw 'rollback_application_still_running' }
        Start-Sleep -Milliseconds 250
    } while ($true)
    $old = Join-Path $recovery 'program'
    $files = @($handoff.old_package.files.PSObject.Properties)
    if ($files.Count -eq 0 -or $files.Count -gt 10000) { throw 'rollback_inventory_invalid' }
    foreach ($file in $files) {
        if ((Get-FileHash -LiteralPath (Owned $old $file.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.Value) { throw 'rollback_program_damaged' }
    }
    $snapshot = Get-Content -LiteralPath (Join-Path $recovery '.dreamtalk-snapshot.json') -Raw | ConvertFrom-Json
    if ($snapshot.identity -ne 'app.livingworld.desktop') { throw 'rollback_snapshot_invalid' }
    foreach ($file in @($snapshot.files.PSObject.Properties)) {
        if ((Get-FileHash -LiteralPath (Owned $recovery $file.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.Value) { throw 'rollback_snapshot_damaged' }
    }
    $preserved = Owned $live ('rollback-preserved-' + [Guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $preserved | Out-Null
    foreach ($name in @('data','config')) {
        $target = Owned $live $name
        if (Test-Path -LiteralPath $target) { [IO.Directory]::Move($target,(Owned $preserved $name)) }
        CopyTree (Owned $recovery $name) $target
    }
    foreach ($file in @($snapshot.files.PSObject.Properties)) {
        if ($file.Name.StartsWith('data/') -or $file.Name.StartsWith('config/')) {
            if ((Get-FileHash -LiteralPath (Owned $live $file.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.Value) { throw 'rollback_data_copy_failed' }
        }
    }
    $savedMarker = Join-Path $recovery '.dreamtalk-storage.json'
    if (Test-Path -LiteralPath $savedMarker) {
        $marker = Owned $live '.dreamtalk-storage.json'
        if (Test-Path -LiteralPath $marker) { [IO.File]::Move($marker,(Owned $preserved '.dreamtalk-storage.json')) }
        [IO.File]::Copy($savedMarker,$marker,$false)
        if ((Get-FileHash -LiteralPath $marker -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $savedMarker -Algorithm SHA256).Hash) { throw 'rollback_data_copy_failed' }
    }
    $currentMarker = Join-Path $program '.dreamtalk-package.json'
    if (Test-Path -LiteralPath $currentMarker) {
        $current = Get-Content -LiteralPath $currentMarker -Raw | ConvertFrom-Json
        if ($current.identity -eq $handoff.identity -and $current.version -eq $handoff.version) {
            foreach ($file in @($current.files.PSObject.Properties)) {
                if ($handoff.old_package.files.PSObject.Properties.Name -contains $file.Name) { continue }
                $target = Owned $program $file.Name
                if ((Test-Path -LiteralPath $target) -and (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -eq $file.Value) {
                    $saved = Owned (Join-Path $preserved 'new-program') $file.Name
                    New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($saved)) -Force | Out-Null
                    [IO.File]::Move($target,$saved)
                }
            }
        }
    }
    foreach ($file in $files) {
        $target = Owned $program $file.Name
        $saved = Owned (Join-Path $preserved 'new-program') $file.Name
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)),([IO.Path]::GetDirectoryName($saved)) -Force | Out-Null
        if (Test-Path -LiteralPath $target) { [IO.File]::Move($target,$saved) }
        [IO.File]::Copy((Owned $old $file.Name),$target,$false)
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.Value) { throw 'rollback_program_copy_failed' }
    }
    [IO.File]::Copy((Join-Path $old '.dreamtalk-package.json'),$currentMarker,$true)
    [IO.File]::Move((Join-Path $live 'updates/handoff.json'),(Join-Path $live ('updates/handoff-rolled-back-' + [Guid]::NewGuid().ToString() + '.json')))
    foreach ($name in @('update-failure.json','restore-hold.json','restore-in-progress.json')) {
        $path = Owned $live $name
        if (Test-Path -LiteralPath $path) { [IO.File]::Move($path,(Owned $preserved $name)) }
    }
    $result = @{status='rolled_back';old_version=$handoff.old_package.version;private_files_preserved=$true}
    Start-Process -FilePath (Owned $program 'dreamtalk-desktop.exe') -WindowStyle Hidden
} catch { $result.error='rollback_incomplete'; $result.details_retained=$true }
finally { $result | ConvertTo-Json | Set-Content -LiteralPath ([IO.Path]::ChangeExtension($RequestPath,'result.json')) -Encoding UTF8 }
