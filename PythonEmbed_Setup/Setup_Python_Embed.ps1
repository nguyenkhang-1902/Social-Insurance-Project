# ============================================================================
# Setup_Python_Embed.ps1
#
# Muc dich: Thay the python-3.15.0b3-embed-amd64 (ban BETA, KHONG co wheel
# pandas/numpy cho Windows) bang Python 3.13.14 embeddable (ban on dinh),
# roi cai san TOAN BO thu vien can thiet (offline, khong can internet tren
# may van phong).
#
# Chi can chay 1 LAN DUY NHAT, tren may co internet (vi du may dev cua ban).
# Sau khi chay xong, ca thu muc App_BHXH (bao gom python-3.13.14-embed-amd64)
# co the copy nguyen sang may cong ty, KHONG can internet, KHONG can cai dat gi them.
#
# Cach chay: mo PowerShell trong thu muc App_BHXH roi go:
#   powershell -ExecutionPolicy Bypass -File .\PythonEmbed_Setup\Setup_Python_Embed.ps1
# ============================================================================

$ErrorActionPreference = "Stop"

$ProjectRoot   = Split-Path -Parent $PSScriptRoot
$PyVersion     = "3.13.14"
$EmbedFolder   = Join-Path $ProjectRoot "python-$PyVersion-embed-amd64"
$EmbedZipUrl   = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip"
$EmbedZipPath  = Join-Path $ProjectRoot "python-$PyVersion-embed-amd64.zip"
$SitePkgZip    = Join-Path $PSScriptRoot "site-packages.zip"
$OldBetaFolder = Join-Path $ProjectRoot "python-3.15.0b3-embed-amd64"

Write-Host "=== Buoc 1/5: Tai Python $PyVersion embeddable (ban chinh thuc tu python.org) ===" -ForegroundColor Cyan
if (-not (Test-Path $EmbedFolder)) {
    Invoke-WebRequest -Uri $EmbedZipUrl -OutFile $EmbedZipPath
    Expand-Archive -Path $EmbedZipPath -DestinationPath $EmbedFolder -Force
    Remove-Item $EmbedZipPath
    Write-Host "Da giai nen vao: $EmbedFolder"
} else {
    Write-Host "Da ton tai $EmbedFolder, bo qua buoc tai."
}

Write-Host "=== Buoc 2/5: Giai nen thu vien da chuan bi san (site-packages.zip) ===" -ForegroundColor Cyan
if (-not (Test-Path $SitePkgZip)) {
    throw "Khong tim thay $SitePkgZip. Hay dam bao file nay nam trong thu muc PythonEmbed_Setup."
}
$SitePackagesDest = Join-Path $EmbedFolder "Lib\site-packages"
New-Item -ItemType Directory -Force -Path $SitePackagesDest | Out-Null
Expand-Archive -Path $SitePkgZip -DestinationPath (Join-Path $EmbedFolder "Lib") -Force
# site-packages.zip chua san thu muc "site-packages" ben trong, di chuyen dung cho neu can
$ExtractedInner = Join-Path $EmbedFolder "Lib\site-packages\site-packages"
if (Test-Path $ExtractedInner) {
    Get-ChildItem $ExtractedInner | Move-Item -Destination $SitePackagesDest -Force
    Remove-Item $ExtractedInner -Recurse -Force
}
Write-Host "Da cai thu vien vao: $SitePackagesDest"

Write-Host "=== Buoc 3/5: Bat site-packages trong file ._pth ===" -ForegroundColor Cyan
$PthFile = Get-ChildItem -Path $EmbedFolder -Filter "python*._pth" | Select-Object -First 1
if (-not $PthFile) { throw "Khong tim thay file ._pth trong $EmbedFolder" }
$PthContent = Get-Content $PthFile.FullName
$NewPthContent = @()
foreach ($line in $PthContent) {
    if ($line.Trim() -eq "#import site") {
        $NewPthContent += "import site"
    } else {
        $NewPthContent += $line
    }
}
if ($NewPthContent -notcontains "Lib\site-packages") {
    $NewPthContent += "Lib\site-packages"
}
Set-Content -Path $PthFile.FullName -Value $NewPthContent -Encoding ASCII
Write-Host "Da cap nhat: $($PthFile.FullName)"

Write-Host "=== Buoc 4/5: Kiem tra import toan bo thu vien ===" -ForegroundColor Cyan
$PythonExe = Join-Path $EmbedFolder "python.exe"
$TestScript = "import fastapi, uvicorn, streamlit, pandas, sqlalchemy, openpyxl, xlsxwriter, requests, numpy, multipart; print('IMPORT_OK')"
$result = & $PythonExe -c $TestScript 2>&1
if ($result -match "IMPORT_OK") {
    Write-Host "THANH CONG: Tat ca thu vien da san sang, khong can internet." -ForegroundColor Green
} else {
    Write-Host "LOI khi import thu vien:" -ForegroundColor Red
    Write-Host $result
    throw "Setup that bai, xem loi phia tren."
}

Write-Host "=== Buoc 5/5: Don dep ===" -ForegroundColor Cyan
if (Test-Path $OldBetaFolder) {
    Write-Host "Phat hien thu muc Python beta cu: $OldBetaFolder"
    Write-Host "Ban co the xoa thu cong thu muc nay sau khi xac nhan moi thu hoat dong tot."
}

Write-Host ""
Write-Host "HOAN TAT. Bay gio co the chay CHAY_CHUONG_TRINH.bat de kiem tra." -ForegroundColor Green
Write-Host "Sau khi xac nhan on, copy nguyen thu muc App_BHXH (tru PythonEmbed_Setup va python-3.15.0b3-embed-amd64) sang may cong ty." -ForegroundColor Green
