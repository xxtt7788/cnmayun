param(
    [string]$OutputPath = "D:\myproject\cnmayun\data\china-succession-deploy.zip"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("china-succession-package-" + [System.Guid]::NewGuid().ToString("N"))

New-Item -ItemType Directory -Path $tempRoot | Out-Null

try {
    $excludeNames = @(".venv", "china_succession.egg-info", "__pycache__", "data", "runner", ".gstack")
    $excludePatterns = @(
        "*.pyc",
        "*.log",
        "*.out.log",
        "*.err.log",
        "china-succession-deploy*.zip",
        "china_succession.db",
        "tmp_*.db",
        "tmp_*.db-journal"
    )

    Get-ChildItem -Path $projectRoot -Force | ForEach-Object {
        if ($excludeNames -contains $_.Name) {
            return
        }
        Copy-Item -LiteralPath $_.FullName -Destination $tempRoot -Recurse -Force
    }

    Get-ChildItem -Path $tempRoot -Recurse -Force | Where-Object {
        $item = $_
        ($excludeNames | Where-Object { $item.FullName -like "*\$_\*" }) -or
        ($excludePatterns | Where-Object { $item.Name -like $_ })
    } | Remove-Item -Force -Recurse

    $deployDb = Join-Path $projectRoot "data\china_succession_deploy.db"
    if (Test-Path $deployDb) {
        $targetDataDir = Join-Path $tempRoot "data"
        if (-not (Test-Path $targetDataDir)) {
            New-Item -ItemType Directory -Path $targetDataDir | Out-Null
        }
        Copy-Item -LiteralPath $deployDb -Destination (Join-Path $targetDataDir "china_succession.db") -Force
    }

    $outputDirectory = Split-Path -Parent $OutputPath
    if ($outputDirectory -and -not (Test-Path $outputDirectory)) {
        New-Item -ItemType Directory -Path $outputDirectory | Out-Null
    }

    if (Test-Path $OutputPath) {
        Remove-Item $OutputPath -Force
    }

    $archive = [System.IO.Compression.ZipFile]::Open($OutputPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        Get-ChildItem -Path $tempRoot -Recurse -File | ForEach-Object {
            $entryName = $_.FullName.Substring($tempRoot.Length).TrimStart('\').Replace('\', '/')
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $_.FullName, $entryName, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
        }
    }
    finally {
        $archive.Dispose()
    }
    Write-Output "Package created: $OutputPath"
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item $tempRoot -Force -Recurse
    }
}
