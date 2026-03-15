param(
    [ValidateSet('balanced', 'aggressive')]
    [string]$Profile = 'balanced',

    [string]$FFmpegRef = 'release/7.1',

    [string]$MSYS2Root = 'C:\msys64',

    [string]$OutputDir,

    [bool]$EnableNvenc = $true,

    [bool]$EnableAmf = $true,

    [bool]$EnableQsv = $true,

    [bool]$EnableX265 = $true,

    [switch]$InstallDeps,

    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Convert-ToMsysPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $normalized = $fullPath -replace '\\', '/'
    if ($normalized -match '^([A-Za-z]):/(.*)$') {
        return "/$($matches[1].ToLowerInvariant())/$($matches[2])"
    }

    return $normalized
}

function Convert-ToBashLiteral {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)

    $replacement = "'" + '"' + "'" + '"' + "'"
    return "'" + $Value.Replace("'", $replacement) + "'"
}

$toolRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$modularAppRoot = Split-Path (Split-Path $toolRoot -Parent) -Parent

if (-not $OutputDir) {
    $OutputDir = Join-Path $modularAppRoot "ffmpeg-custom\$Profile"
}

$workRoot = Join-Path $toolRoot 'work'
$sourceDir = Join-Path $workRoot 'src\ffmpeg'
$buildDir = Join-Path $workRoot "build\$Profile"
$prefixDir = Join-Path $workRoot "prefix\$Profile"
$bashScript = Join-Path $toolRoot 'build_ffmpeg_msys2.sh'
$bashExe = Join-Path $MSYS2Root 'usr\bin\bash.exe'

if (-not (Test-Path -LiteralPath $bashExe)) {
    throw @"
MSYS2 bash bulunamadi: $bashExe

Kurulum:
  winget install -e --id MSYS2.MSYS2

Sonrasinda MSYS2'yi en az bir kez guncelleyip bu scripti tekrar calistir.
"@
}

if (-not (Test-Path -LiteralPath $bashScript)) {
    throw "Build script bulunamadi: $bashScript"
}

$envMap = [ordered]@{
    MSYSTEM      = 'UCRT64'
    CHERE_INVOKING = '1'
    MSYS2_PATH_TYPE = 'inherit'
    PROFILE      = $Profile
    FFMPEG_REF   = $FFmpegRef
    WORK_DIR     = Convert-ToMsysPath $workRoot
    SRC_DIR      = Convert-ToMsysPath $sourceDir
    BUILD_DIR    = Convert-ToMsysPath $buildDir
    PREFIX_DIR   = Convert-ToMsysPath $prefixDir
    OUTPUT_DIR   = Convert-ToMsysPath $OutputDir
    ENABLE_NVENC = if ($EnableNvenc) { '1' } else { '0' }
    ENABLE_AMF   = if ($EnableAmf) { '1' } else { '0' }
    ENABLE_QSV   = if ($EnableQsv) { '1' } else { '0' }
    ENABLE_X265  = if ($EnableX265) { '1' } else { '0' }
    INSTALL_DEPS = if ($InstallDeps.IsPresent) { '1' } else { '0' }
    CLEAN        = if ($Clean.IsPresent) { '1' } else { '0' }
}

$exportLines = foreach ($item in $envMap.GetEnumerator()) {
    "export $($item.Key)=" + (Convert-ToBashLiteral $item.Value)
}

$bashScriptMsys = Convert-ToMsysPath $bashScript
$commandParts = @(
    'set -euo pipefail'
    $exportLines
    "bash $(Convert-ToBashLiteral $bashScriptMsys)"
)
$bashCommand = $commandParts -join '; '

Write-Host "Profile      : $Profile"
Write-Host "FFmpeg ref   : $FFmpegRef"
Write-Host "Output       : $OutputDir"
Write-Host "NVENC        : $EnableNvenc"
Write-Host "AMF          : $EnableAmf"
Write-Host "QSV          : $EnableQsv"
Write-Host "libx265      : $EnableX265"
Write-Host "Install deps : $($InstallDeps.IsPresent)"
Write-Host ''

& $bashExe --login -lc $bashCommand
if ($LASTEXITCODE -ne 0) {
    throw "FFmpeg build basarisiz oldu. Cikis kodu: $LASTEXITCODE"
}

Write-Host ''
Write-Host "Hazirlandi: $OutputDir"
Write-Host "Uygulamada bu klasordeki ffmpeg.exe ve ffprobe.exe dosyalarini kullanabilirsiniz."
