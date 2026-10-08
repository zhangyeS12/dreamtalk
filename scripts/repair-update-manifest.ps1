# Repairs only the two original, fingerprinted NSIS manifests affected by the
# Tauri bundle-type patch. Does not execute an installer or access app-data.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallDirectory,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$identity = 'app.livingworld.desktop'
$backupRelative = '.dreamtalk-package.before-nsis-fix.json'
$known = @{
    '0.1.46' = @{
        Manifest = '70ee054ff9fef543369c6162bd538b7bda58ffdc7519f42ab6a9dd6efc028d4b'
        Original = '82a91b5ccbcdf140f0cb3a2411f4c3f3828b3fe67f25f403064cb0fd7dcc1da1'
        Installed = '8048749083df361e86fab4f2958f95b407e832d810c2725180a7b6444be8c33c'
    }
    '0.1.47' = @{
        Manifest = '2baeab5912c31a064af08926a12ced069d2df3c298abd2d5a5d8b1fdfedc7797'
        Original = 'b0bf02dfee0c55d160a0ddea08033e049109cf6da542ee65a4aaf51eb57a0ae4'
        Installed = '9491f3dfb0ea6f616ca833ecff3b16cc4bccf38ddecd48bdd73881d97b2b6364'
    }
}
function Bytes-Hash([byte[]]$Bytes) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function File-Hash([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}
$root = [System.IO.Path]::GetFullPath($InstallDirectory).TrimEnd('\', '/')
if (-not [System.IO.Directory]::Exists($root) -or
    $root -eq [System.IO.Path]::GetPathRoot($root).TrimEnd('\', '/')) {
    throw 'repair_install_directory_invalid'
}
$ancestor = $root
while ($ancestor) {
    if (([System.IO.File]::GetAttributes($ancestor) -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
        (Test-Path -LiteralPath (Join-Path $ancestor '.git'))) {
        throw 'repair_link_or_repository_rejected'
    }
    $ancestor = [System.IO.Path]::GetDirectoryName($ancestor)
}
function Owned-Path([string]$Relative) {
    if ($Relative.Contains('\') -or $Relative.Contains(':') -or
        @($Relative.Split('/') | Where-Object { $_ -eq '' -or $_ -eq '.' -or $_ -eq '..' }).Count) {
        throw 'repair_manifest_path_invalid'
    }
    $path = $root
    foreach ($part in $Relative.Split('/')) {
        $path = Join-Path $path $part
        if ((Test-Path -LiteralPath $path) -and
            (([System.IO.File]::GetAttributes($path) -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw 'repair_manifest_link_rejected'
        }
    }
    if (-not [System.IO.Path]::GetFullPath($path).StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'repair_manifest_path_invalid'
    }
    return $path
}
$markerPath = Owned-Path '.dreamtalk-package.json'
$backupPath = Owned-Path $backupRelative
$currentBytes = [System.IO.File]::ReadAllBytes($markerPath)
$currentHash = Bytes-Hash $currentBytes
$current = [System.Text.Encoding]::UTF8.GetString($currentBytes) | ConvertFrom-Json
if ($current.identity -cne $identity -or -not $known.ContainsKey([string]$current.version)) {
    throw 'repair_release_not_supported'
}
$release = $known[[string]$current.version]
$alreadyRepaired = $currentHash -cne $release.Manifest
if ($alreadyRepaired) {
    $originalBytes = [System.IO.File]::ReadAllBytes($backupPath)
    if ((Bytes-Hash $originalBytes) -cne $release.Manifest) { throw 'repair_original_manifest_not_known' }
} else {
    $originalBytes = $currentBytes
}
$original = [System.Text.Encoding]::UTF8.GetString($originalBytes) | ConvertFrom-Json
if ($original.identity -cne $identity -or $original.version -cne $current.version -or
    $original.files.'dreamtalk-desktop.exe' -cne $release.Original -or
    $null -eq $original.files.'.dreamtalk-installed') {
    throw 'repair_original_manifest_invalid'
}
$original.files.'dreamtalk-desktop.exe' = $release.Installed
$original.files | Add-Member -MemberType NoteProperty -Name $backupRelative -Value $release.Manifest
$expectedFiles = @($original.files.PSObject.Properties)
if ($alreadyRepaired) {
    if (@($current.PSObject.Properties).Count -ne 3 -or
        @($current.files.PSObject.Properties).Count -ne $expectedFiles.Count) {
        throw 'repair_manifest_changed'
    }
    foreach ($entry in $expectedFiles) {
        if ($current.files.PSObject.Properties[$entry.Name].Value -cne $entry.Value) {
            throw 'repair_manifest_changed'
        }
    }
}
foreach ($entry in $expectedFiles) {
    if ($entry.Name -eq $backupRelative -and -not $alreadyRepaired -and
        -not (Test-Path -LiteralPath $backupPath)) { continue }
    $path = Owned-Path $entry.Name
    if (-not [System.IO.File]::Exists($path) -or (File-Hash $path) -cne $entry.Value) {
        throw ('repair_file_not_original: ' + $entry.Name)
    }
}
Write-Output ('verified_release=' + $current.version + '; verified_files=' + ($expectedFiles.Count - 1))
if ($alreadyRepaired) { Write-Output 'manifest_already_repaired'; return }
if (-not $Apply) { Write-Output 'repair_available; rerun_with_Apply_to_write_manifest'; return }
if ((File-Hash $markerPath) -cne $currentHash) { throw 'repair_manifest_changed_during_check' }
if (-not (Test-Path -LiteralPath $backupPath)) {
    $backup = [System.IO.File]::Open($backupPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try { $backup.Write($originalBytes, 0, $originalBytes.Length); $backup.Flush($true) }
    finally { $backup.Dispose() }
}
$temporaryPath = Owned-Path ('.dreamtalk-package.repair-' + [Guid]::NewGuid().ToString('N') + '.tmp')
try {
    $repairedBytes = [System.Text.UTF8Encoding]::new($false).GetBytes(($original | ConvertTo-Json -Depth 10) + "`n")
    $temporary = [System.IO.File]::Open($temporaryPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try { $temporary.Write($repairedBytes, 0, $repairedBytes.Length); $temporary.Flush($true) }
    finally { $temporary.Dispose() }
    [System.IO.File]::Replace($temporaryPath, $markerPath, $null)
} finally {
    if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath }
}
Write-Output 'manifest_repaired; original_manifest_preserved; program_and_app_data_unchanged'
