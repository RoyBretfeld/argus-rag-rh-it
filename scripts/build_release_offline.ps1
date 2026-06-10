# build_release_offline.ps1 — Offline-Komplettpaket (~12-15 GB)
# ==============================================================
# Baut auf build_release.ps1 auf und ergaenzt:
#   wheels/         alle Python-Pakete (pip download, Win x64 / Py 3.12)
#   installers/     python-3.12.10-amd64.exe + OllamaSetup.exe
#   ollama_models/  NUR mistral, moondream, nomic-embed-text (selektiv via Manifest)
#   setup.bat       Offline-Variante (installiert alles ohne Internet)
#
# Aufruf:  powershell -ExecutionPolicy Bypass -File scripts\build_release_offline.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$stamp = Get-Date -Format "yyyyMMdd"

# ---------- 0. Portables Basis-Release bauen ----------
& (Join-Path $PSScriptRoot "build_release.ps1")

$src = Join-Path $root "_release\ArgusRAG-portable-$stamp"
$name = "ArgusRAG-offline-$stamp"
$rel = Join-Path $root "_release\$name"
Write-Host "`n[OFFLINE 1/5] Basis kopieren -> $rel"
if (Test-Path $rel) { Remove-Item $rel -Recurse -Force }
robocopy $src $rel /E | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy Basis fehlgeschlagen" }
# Offline-Setup ersetzt das Online-Setup
Copy-Item (Join-Path $PSScriptRoot "release\setup_offline.bat") (Join-Path $rel "setup.bat") -Force

# ---------- 1. Python-Wheels herunterladen ----------
Write-Host "[OFFLINE 2/5] Python-Pakete herunterladen (mehrere GB)..."
$wheels = Join-Path $rel "wheels"
New-Item -ItemType Directory -Force $wheels | Out-Null
py -3.12 -m pip download -r (Join-Path $root "requirements.txt") -d $wheels --prefer-binary --quiet
if ($LASTEXITCODE) { throw "pip download requirements fehlgeschlagen" }
# Basis-Tooling fuer evtl. sdist-Builds offline mitgeben
py -3.12 -m pip download pip setuptools wheel -d $wheels --prefer-binary --quiet
if ($LASTEXITCODE) { throw "pip download tooling fehlgeschlagen" }

# ---------- 2. Installer herunterladen ----------
Write-Host "[OFFLINE 3/5] Installer herunterladen (Python + Ollama)..."
$inst = Join-Path $rel "installers"
New-Item -ItemType Directory -Force $inst | Out-Null
$pyExe = Join-Path $inst "python-3.12.10-amd64.exe"
if (-not (Test-Path $pyExe)) {
    Invoke-WebRequest "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" -OutFile $pyExe
}
$olExe = Join-Path $inst "OllamaSetup.exe"
if (-not (Test-Path $olExe)) {
    Invoke-WebRequest "https://ollama.com/download/OllamaSetup.exe" -OutFile $olExe
}

# ---------- 3. Ollama-Modelle selektiv kopieren ----------
Write-Host "[OFFLINE 4/5] Modelle einpacken (mistral, moondream, nomic-embed-text)..."
$store = $env:OLLAMA_MODELS
if (-not $store) { $store = Join-Path $env:USERPROFILE ".ollama\models" }
if (-not (Test-Path "$store\manifests")) { throw "Ollama-Modell-Store nicht gefunden: $store" }

$dstModels = Join-Path $rel "ollama_models"
foreach ($model in @("mistral", "moondream", "nomic-embed-text")) {
    $manifestDir = Join-Path $store "manifests\registry.ollama.ai\library\$model"
    if (-not (Test-Path $manifestDir)) { throw "Modell fehlt lokal: $model — bitte erst 'ollama pull $model'" }
    $dstManifestDir = Join-Path $dstModels "manifests\registry.ollama.ai\library\$model"
    New-Item -ItemType Directory -Force $dstManifestDir | Out-Null
    foreach ($mf in Get-ChildItem $manifestDir -File) {
        Copy-Item $mf.FullName $dstManifestDir -Force
        # Manifest parsen: alle referenzierten Blobs (config + layers) kopieren
        $json = Get-Content $mf.FullName -Raw | ConvertFrom-Json
        $digests = @($json.config.digest) + @($json.layers | ForEach-Object { $_.digest })
        foreach ($d in $digests) {
            if (-not $d) { continue }
            $blobName = $d -replace ":", "-"
            $srcBlob = Join-Path $store "blobs\$blobName"
            $dstBlobDir = Join-Path $dstModels "blobs"
            New-Item -ItemType Directory -Force $dstBlobDir | Out-Null
            if (-not (Test-Path (Join-Path $dstBlobDir $blobName))) {
                if (-not (Test-Path $srcBlob)) { throw "Blob fehlt: $srcBlob ($model)" }
                Copy-Item $srcBlob $dstBlobDir
            }
        }
    }
    Write-Host "  + $model"
}

# ---------- 4. ZIP (ohne Kompression — Inhalt ist bereits komprimiert) ----------
Write-Host "[OFFLINE 5/5] Erstelle ZIP (kann einige Minuten dauern)..."
$zip = Join-Path $root "_release\$name.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $rel -DestinationPath $zip -CompressionLevel NoCompression
$sizeGB = (Get-Item $zip).Length / 1GB
Write-Host ("FERTIG: {0} ({1:N1} GB)" -f $zip, $sizeGB)
Write-Host "Zielrechner (offline): entpacken -> setup.bat -> start_argus.bat"
