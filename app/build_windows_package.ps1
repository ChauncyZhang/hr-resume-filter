param(
  [string]$PackageName = "hr-resume-filter-windows"
)

$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Split-Path -Parent $AppDir
$BuildDir = Join-Path $RepoDir "build\windows"
$VenvDir = Join-Path $BuildDir ".venv"
$PyInstallerDist = Join-Path $BuildDir "pyinstaller-dist"
$PyInstallerWork = Join-Path $BuildDir "pyinstaller-work"
$PackageDir = Join-Path $RepoDir "dist\$PackageName"
$ZipPath = Join-Path $RepoDir "dist\$PackageName.zip"
$ExeName = "HRResumeFilter"

New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $PackageDir) | Out-Null

if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
  Write-Host "Creating build virtual environment..."
  py -3 -m venv $VenvDir
}

$Python = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "Installing build dependencies..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $AppDir "requirements.txt") pyinstaller

if (Test-Path $PyInstallerDist) {
  Remove-Item -LiteralPath $PyInstallerDist -Recurse -Force
}
if (Test-Path $PyInstallerWork) {
  Remove-Item -LiteralPath $PyInstallerWork -Recurse -Force
}
if (Test-Path $PackageDir) {
  Remove-Item -LiteralPath $PackageDir -Recurse -Force
}

Write-Host "Building Windows portable app..."
& $Python -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --console `
  --name $ExeName `
  --distpath $PyInstallerDist `
  --workpath $PyInstallerWork `
  --paths $AppDir `
  --add-data "$(Join-Path $AppDir 'web');web" `
  --add-data "$(Join-Path $AppDir 'data\config.example.json');data" `
  (Join-Path $AppDir "web_app.py")

$Launcher = Get-ChildItem -LiteralPath $RepoDir -Filter "Windows*.bat" | Select-Object -First 1
if (-not $Launcher) {
  throw "Windows launcher was not found."
}

New-Item -ItemType Directory -Force -Path (Join-Path $PackageDir "app") | Out-Null
Copy-Item -LiteralPath $Launcher.FullName -Destination $PackageDir
$BuiltAppDir = Join-Path $PyInstallerDist $ExeName
Copy-Item -Path (Join-Path $BuiltAppDir "*") -Destination (Join-Path $PackageDir "app") -Recurse
Copy-Item -LiteralPath (Join-Path $AppDir "README.md") -Destination (Join-Path $PackageDir "app")

if (Test-Path $ZipPath) {
  Remove-Item -LiteralPath $ZipPath -Force
}

Write-Host "Creating zip package..."
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath

Write-Host ""
Write-Host "Created: $ZipPath"
Write-Host "Send this zip to HR. They only need to unzip it and double-click the Windows launcher."
