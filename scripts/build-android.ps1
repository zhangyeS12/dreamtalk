#Requires -Version 7.0
param([switch]$SkipCI)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$env:PYTHONUTF8 = '1'
if ($SkipCI) {
    $releaseVersion = (Get-Content -LiteralPath (Join-Path $root 'package.json') -Raw | ConvertFrom-Json).version
    $authorizationFile = Join-Path $root ('artifacts/github-android-personal-' + $releaseVersion.Replace('.','') + '/release-authorization.json')
    $authorization = Get-Content -LiteralPath $authorizationFile -Raw | ConvertFrom-Json
    if ($authorization.version -ne $releaseVersion -or -not $authorization.user_authorized_release -or -not $authorization.user_authorized_skip_ci) { throw 'Explicit release CI exception missing' }
    Write-Host 'CI skipped for this release by explicit user instruction; local build/signature/payload checks remain enabled.'
} else {
    & 'D:/LivingWorld/.venv/Scripts/python.exe' scripts/check-android-release-ci.py
    if ($LASTEXITCODE -ne 0) { throw 'Exact-commit Android CI or source verification failed' }
}
$env:JAVA_HOME = (Get-ChildItem -LiteralPath (Join-Path $root 'build-tools/jdk21') -Directory | Select-Object -First 1).FullName
$env:ANDROID_HOME = Join-Path $root 'build-tools/android-sdk'
$location = Get-Content -LiteralPath (Join-Path $root 'build-tools/temporary-build-location.json') -Raw | ConvertFrom-Json
$cache = [IO.Path]::GetFullPath($location.directory)
$marker = Get-Content -LiteralPath (Join-Path $cache '.dreamtalk-build-cache.json') -Raw | ConvertFrom-Json
if (-not $marker.temporary_build_only -or [IO.Path]::GetFullPath($marker.source) -ne [IO.Path]::GetFullPath($root)) { throw 'Unverified Android build cache' }
$env:NDK_HOME = Join-Path $cache 'ndk'
$env:CARGO_TARGET_DIR = Join-Path $cache 'cargo'
$env:GRADLE_USER_HOME = Join-Path $root 'build-tools/gradle-user'
$env:DREAMTALK_BUILD_PYTHON = 'D:\LivingWorld\.venv\Scripts\python.exe'
$env:RUSTFLAGS = '-C link-arg=-Wl,-z,max-page-size=16384'
$env:JAVA_TOOL_OPTIONS = '-Dfile.encoding=UTF-8'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
& $env:DREAMTALK_BUILD_PYTHON scripts/build-mobile-wheel.py
if ($LASTEXITCODE -ne 0) { throw 'Core wheel failed' }
npm.cmd run typecheck *> artifacts/typecheck.log
if ($LASTEXITCODE -ne 0) { throw 'TypeScript check failed; see artifacts/typecheck.log' }
npm.cmd run build:android --workspace '@dreamtalk/mobile' *> artifacts/android-final-native-build.log
if ($LASTEXITCODE -ne 0) {
    $nativeLog = Get-Content -LiteralPath artifacts/android-final-native-build.log -Raw
    if ($nativeLog -notmatch 'Finished `release`' -or $nativeLog -notmatch 'Creation symbolic link is not allowed for this system') { throw 'Native build failed; see artifacts/android-final-native-build.log' }
    Write-Host 'Native compilation passed. Using file-copy fallback for Windows symbolic-link restriction.'
}
$android = Join-Path $root 'apps/mobile/src-tauri/gen/android'
Copy-Item -LiteralPath (Join-Path $env:CARGO_TARGET_DIR 'aarch64-linux-android/release/libdreamtalk_mobile.so') -Destination (Join-Path $android 'app/src/main/jniLibs/arm64-v8a/libdreamtalk_mobile.so') -Force
# Tauri normally stages this alongside the Rust .so. The Windows copy fallback
# must stage both files; Python's private archive is unavailable to the linker at startup.
Copy-Item -LiteralPath (Join-Path $env:NDK_HOME 'toolchains/llvm/prebuilt/windows-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so') -Destination (Join-Path $android 'app/src/main/jniLibs/arm64-v8a/libc++_shared.so') -Force
$env:DREAMTALK_PREBUILT_RUST = '1'
& (Join-Path $android 'gradlew.bat') -p $android :app:assembleArm64Release --no-daemon --console=plain *> artifacts/gradle-final-build.log
if ($LASTEXITCODE -ne 0) { throw 'APK build failed; see artifacts/gradle-final-build.log' }
$output = Join-Path $root 'artifacts/android-preview'
New-Item -ItemType Directory -Path $output -Force | Out-Null
$unsigned = Join-Path $android 'app/build/outputs/apk/arm64/release/app-arm64-release-unsigned.apk'
$aligned = Join-Path $output 'preview-aligned-unsigned.apk'
$version = (Get-Content -LiteralPath (Join-Path $root 'apps/mobile/src-tauri/tauri.conf.json') -Raw | ConvertFrom-Json).version
$final = Join-Path $output ("dreamtalk-android-$version-arm64.apk")
$tools = Join-Path $env:ANDROID_HOME 'build-tools/35.0.0'
& (Join-Path $tools 'zipalign.exe') -P 16 -f 4 $unsigned $aligned
if ($LASTEXITCODE -ne 0) { throw 'APK alignment failed' }
try {
    $protected = [IO.File]::ReadAllBytes((Join-Path $root 'private/android-preview.password.dpapi'))
    $env:DREAMTALK_PREVIEW_STORE_PASSWORD = [Text.Encoding]::UTF8.GetString([Security.Cryptography.ProtectedData]::Unprotect($protected,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser))
    & (Join-Path $tools 'apksigner.bat') sign --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false --ks (Join-Path $root 'private/android-preview.p12') --ks-key-alias dreamtalk-preview --ks-pass env:DREAMTALK_PREVIEW_STORE_PASSWORD --out $final $aligned
    if ($LASTEXITCODE -ne 0) { throw 'APK signing failed' }
} finally { Remove-Item Env:DREAMTALK_PREVIEW_STORE_PASSWORD -ErrorAction SilentlyContinue }
& (Join-Path $tools 'apksigner.bat') verify --verbose --print-certs $final *> artifacts/apk-signature-check.log
if ($LASTEXITCODE -ne 0) { throw 'APK signature verification failed' }
foreach ($range in @(@(23,23), @(24,27), @(28,36))) {
    $schemeLog = "artifacts/apk-signature-sdk-$($range[0])-$($range[1]).log"
    & (Join-Path $tools 'apksigner.bat') verify --verbose --print-certs --min-sdk-version $range[0] --max-sdk-version $range[1] $final *> $schemeLog
    if ($LASTEXITCODE -ne 0) { throw "APK signature compatibility verification failed: $schemeLog" }
}
& (Join-Path $tools 'zipalign.exe') -c -P 16 4 $final
if ($LASTEXITCODE -ne 0) { throw 'Signed APK alignment verification failed' }
& $env:DREAMTALK_BUILD_PYTHON scripts/verify-mobile-apk.py $final
if ($LASTEXITCODE -ne 0) { throw 'APK static payload verification failed' }
Remove-Item -LiteralPath $aligned
Write-Host "Signed preview: $final"
