#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$output = Join-Path $root 'artifacts/android-local'
$logs = Join-Path $output 'logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$env:PYTHONUTF8 = '1'
$python = Join-Path $root '.venv-check/Scripts/python.exe'
$env:JAVA_HOME = (Get-ChildItem -LiteralPath (Join-Path $root 'build-tools/jdk21') -Directory | Select-Object -First 1).FullName
$env:ANDROID_HOME = Join-Path $root 'build-tools/android-sdk'
$location = Get-Content -LiteralPath (Join-Path $root 'build-tools/temporary-build-location.json') -Raw | ConvertFrom-Json
$cache = [IO.Path]::GetFullPath($location.directory)
$marker = Get-Content -LiteralPath (Join-Path $cache '.dreamtalk-build-cache.json') -Raw | ConvertFrom-Json
if (-not $marker.temporary_build_only -or [IO.Path]::GetFullPath($marker.source) -ne [IO.Path]::GetFullPath($root)) { throw 'Unverified Android build cache' }
$env:NDK_HOME = Join-Path $cache 'ndk'
$env:CARGO_TARGET_DIR = Join-Path $cache 'cargo'
$env:GRADLE_USER_HOME = Join-Path $root 'build-tools/gradle-user'
$env:DREAMTALK_BUILD_PYTHON = $python
$env:RUSTFLAGS = '-C link-arg=-Wl,-z,max-page-size=16384'
$env:JAVA_TOOL_OPTIONS = '-Dfile.encoding=UTF-8'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
Write-Host 'Local Android acceptance build. No CI, GitHub, release version changes, or release signing key.'
& $python scripts/prepare-mobile-recall.py
if ($LASTEXITCODE -ne 0) { throw 'Fixed semantic retrieval resources invalid' }
& $python scripts/android-local.py fingerprint --output (Join-Path $output 'source-before.json')
if ($LASTEXITCODE -ne 0) { throw 'Source fingerprint failed' }
& $python scripts/build-mobile-wheel.py *> (Join-Path $logs 'core-wheel.log')
if ($LASTEXITCODE -ne 0) { throw 'Core wheel failed; see local logs' }
npm.cmd run typecheck *> (Join-Path $logs 'typecheck.log')
if ($LASTEXITCODE -ne 0) { throw 'TypeScript check failed; see local logs' }
npm.cmd run build:android --workspace '@dreamtalk/mobile' *> (Join-Path $logs 'native-build.log')
if ($LASTEXITCODE -ne 0) {
    $nativeLog = Get-Content -LiteralPath (Join-Path $logs 'native-build.log') -Raw
    if ($nativeLog -notmatch 'Finished .release.' -or $nativeLog -notmatch 'Creation symbolic link is not allowed for this system') { throw 'Native build failed; see local logs' }
    Write-Host 'Native compilation passed; staging libraries by file copy.'
}
$android = Join-Path $root 'apps/mobile/src-tauri/gen/android'
$jni = Join-Path $android 'app/src/main/jniLibs/arm64-v8a'
New-Item -ItemType Directory -Path $jni -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $env:CARGO_TARGET_DIR 'aarch64-linux-android/release/libdreamtalk_mobile.so') -Destination (Join-Path $jni 'libdreamtalk_mobile.so') -Force
Copy-Item -LiteralPath (Join-Path $env:NDK_HOME 'toolchains/llvm/prebuilt/windows-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so') -Destination (Join-Path $jni 'libc++_shared.so') -Force
$env:DREAMTALK_PREBUILT_RUST = '1'
& (Join-Path $android 'gradlew.bat') -p $android :app:assembleArm64Release --offline --no-daemon --console=plain *> (Join-Path $logs 'gradle-build.log')
if ($LASTEXITCODE -ne 0) { throw 'Local APK build failed; see local logs' }
$tools = Join-Path $env:ANDROID_HOME 'build-tools/35.0.0'
$unsigned = Join-Path $android 'app/build/outputs/apk/arm64/release/app-arm64-release-unsigned.apk'
$aligned = Join-Path $output 'aligned-unsigned.apk'
$candidate = Join-Path $output 'candidate.apk'
$final = Join-Path $output 'dreamtalk-android-local.apk'
& (Join-Path $tools 'zipalign.exe') -P 16 -f 4 $unsigned $aligned
if ($LASTEXITCODE -ne 0) { throw 'Local APK alignment failed' }
# This separate, conventional debug-password key is for this isolated emulator only.
$keyDirectory = Join-Path $root 'build-tools/local-acceptance/signing'
New-Item -ItemType Directory -Path $keyDirectory -Force | Out-Null
$key = Join-Path $keyDirectory 'local-acceptance.p12'
if (-not (Test-Path -LiteralPath $key)) {
    & (Join-Path $env:JAVA_HOME 'bin/keytool.exe') -genkeypair -keystore $key -storetype PKCS12 -storepass android -keypass android -alias dreamtalk-local -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=dreamtalk Local Acceptance' *> (Join-Path $logs 'local-key.log')
    if ($LASTEXITCODE -ne 0) { throw 'Local-only signing key creation failed' }
}
& (Join-Path $tools 'apksigner.bat') sign --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false --ks $key --ks-key-alias dreamtalk-local --ks-pass pass:android --out $candidate $aligned
if ($LASTEXITCODE -ne 0) { throw 'Local APK signing failed' }
& (Join-Path $tools 'apksigner.bat') verify --verbose --print-certs $candidate *> (Join-Path $logs 'signature.log')
if ($LASTEXITCODE -ne 0) { throw 'Local APK signature verification failed' }
& (Join-Path $tools 'zipalign.exe') -c -P 16 4 $candidate
if ($LASTEXITCODE -ne 0) { throw 'Signed local APK alignment failed' }
& $python scripts/verify-mobile-apk.py $candidate --report (Join-Path $output 'apk-verification.json') *> (Join-Path $logs 'payload.log')
if ($LASTEXITCODE -ne 0) { throw 'Local APK payload validation failed' }
& $python scripts/android-local.py record-build --apk $candidate
if ($LASTEXITCODE -ne 0) { throw 'Source changed during build; prior local test entry preserved' }
Copy-Item -LiteralPath $candidate -Destination $final -Force
& $python scripts/android-local.py finalize-build
if ($LASTEXITCODE -ne 0) { throw 'Local build receipt could not be finalized' }
Write-Host "Local acceptance APK ready: $final"
