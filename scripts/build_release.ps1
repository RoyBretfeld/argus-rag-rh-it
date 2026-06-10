# build_release.ps1 — Baut das portable Argus-RAG-Release-ZIP
# ============================================================
# 1. Frontend produktiv bauen (vite build -> frontend/dist)
# 2. Release-Ordner zusammenstellen (ohne data/, logs/, tests/, node_modules, .git)
#    -> Vektor-DB startet auf dem Zielrechner garantiert bei null
# 3. setup.bat / start_argus.bat ins Release-Root legen
# 4. ZIP nach _release/ schreiben
#
# Aufruf:  powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

# ---------- 1. Frontend bauen ----------
Write-Host "[1/4] Frontend bauen (vite build)..."
Push-Location (Join-Path $root "frontend")
try {
    if (-not (Test-Path "node_modules")) { npm install; if ($LASTEXITCODE) { throw "npm install fehlgeschlagen" } }
    npm run build
    if ($LASTEXITCODE) { throw "npm run build fehlgeschlagen" }
} finally { Pop-Location }
if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) { throw "frontend/dist/index.html fehlt nach Build" }

# ---------- 2. Release-Ordner ----------
$stamp = Get-Date -Format "yyyyMMdd"
$name = "ArgusRAG-portable-$stamp"
$relRoot = Join-Path $root "_release"
$rel = Join-Path $relRoot $name
Write-Host "[2/4] Release-Ordner: $rel"
if (Test-Path $rel) { Remove-Item $rel -Recurse -Force }
New-Item -ItemType Directory -Force $rel | Out-Null

# Python-Code (ohne __pycache__)
robocopy (Join-Path $root "api")  (Join-Path $rel "api")  /E /XD __pycache__ | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy api fehlgeschlagen" }
robocopy (Join-Path $root "core") (Join-Path $rel "core") /E /XD __pycache__ | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy core fehlgeschlagen" }
# Gebautes Frontend
robocopy (Join-Path $root "frontend\dist") (Join-Path $rel "frontend\dist") /E | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy dist fehlgeschlagen" }
$LASTEXITCODE = 0   # robocopy-Erfolgscodes (1-7) nicht als Fehler weiterreichen

# Einzeldateien
foreach ($f in @("requirements.txt", ".env.example", "README.md")) {
    Copy-Item (Join-Path $root $f) $rel
}
Copy-Item (Join-Path $PSScriptRoot "release\setup.bat") $rel
Copy-Item (Join-Path $PSScriptRoot "release\start_argus.bat") $rel

# ---------- 3. Plausibilitaet: keine Daten/Secrets im Release ----------
Write-Host "[3/4] Pruefe Release-Inhalt..."
foreach ($verboten in @("data", "logs", ".env", "tests", ".git")) {
    if (Test-Path (Join-Path $rel $verboten)) { throw "VERBOTEN im Release: $verboten" }
}

# ---------- 4. ZIP ----------
$zip = Join-Path $relRoot "$name.zip"
Write-Host "[4/4] Erstelle $zip ..."
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $rel -DestinationPath $zip
$size = (Get-Item $zip).Length / 1MB
Write-Host ("FERTIG: {0} ({1:N1} MB)" -f $zip, $size)
Write-Host "Auf dem Zielrechner: entpacken -> setup.bat -> start_argus.bat"
