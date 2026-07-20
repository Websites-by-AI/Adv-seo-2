param(
    [string]$SourceDir = (Get-Location).Path,
    [string]$WorkDir = (Join-Path (Get-Location).Path ".hf-space-upload"),
    [string]$SpaceId = "SoSa123456/clinic-lead-agent"
)

$ErrorActionPreference = "Stop"
$GitUrl = "https://huggingface.co/spaces/$SpaceId"
$SpaceUrl = "https://huggingface.co/spaces/$SpaceId"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is required. Install it with: winget install --id Git.Git -e"
}

if (-not (Get-Command hf -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Hugging Face CLI..."
    py -m pip install --user --upgrade huggingface_hub
    $UserScripts = Join-Path $env:APPDATA "Python\Python313\Scripts"
    if (Test-Path $UserScripts) { $env:Path = "$UserScripts;$env:Path" }
}

try {
    hf auth whoami | Out-Null
} catch {
    Write-Host "Create a WRITE token at https://huggingface.co/settings/tokens"
    hf auth login
}

try { git lfs install | Out-Null } catch { }

if (Test-Path (Join-Path $WorkDir ".git")) {
    Write-Host "Updating existing clone..."
    git -C $WorkDir pull --rebase
} else {
    if (Test-Path $WorkDir) { Remove-Item $WorkDir -Recurse -Force }
    git clone $GitUrl $WorkDir
}

# Delete previous files but preserve .git.
Get-ChildItem -Path $WorkDir -Force | Where-Object { $_.Name -ne ".git" } | Remove-Item -Recurse -Force

# Copy source files. The provided project ZIP contains no Git metadata or secrets.
Get-ChildItem -Path $SourceDir -Force | Where-Object {
    $_.Name -notin @(".git", ".env", "node_modules", "__pycache__", ".hf-space-upload") -and
    $_.Extension -ne ".zip"
} | ForEach-Object {
    Copy-Item $_.FullName -Destination $WorkDir -Recurse -Force
}

Push-Location $WorkDir
try {
    git add -A
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "No changes to upload."
    } else {
        $GitName = git config user.name
        $GitEmail = git config user.email
        if (-not $GitName -or -not $GitEmail) {
            throw @"
Git identity is missing. Run these commands once:
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
Then rerun this script.
"@
        }
        git commit -m "Deploy Clinic Signal to Hugging Face Space"
        git push origin main
    }
} finally {
    Pop-Location
}

Write-Host "Deployment pushed successfully."
Write-Host "Space: $SpaceUrl"
Write-Host "App URL after build: https://sosa123456-clinic-lead-agent.hf.space"
