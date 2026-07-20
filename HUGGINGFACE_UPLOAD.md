# Upload Clinic Signal to Hugging Face Spaces

Space repository:

- https://huggingface.co/spaces/SoSa123456/clinic-lead-agent
- Web upload: https://huggingface.co/spaces/SoSa123456/clinic-lead-agent/upload/main
- App URL after build: https://sosa123456-clinic-lead-agent.hf.space

## Prerequisite: create the Space

If it does not exist, create it at https://huggingface.co/new-space with:

- Owner: `SoSa123456`
- Space name: `clinic-lead-agent`
- SDK: `Docker`
- Hardware: free CPU

## Token

Create a User Access Token at:

https://huggingface.co/settings/tokens

Select **Write** permission. Do not commit or paste the token into a URL. Authenticate with:

```bash
hf auth login
```

## Method 1 — Bash / Git Bash / Linux / macOS

From the extracted project folder:

```bash
python -m pip install --upgrade huggingface_hub
git lfs install
hf auth login

chmod +x upload_huggingface.sh
./upload_huggingface.sh
```

Or run manually:

```bash
git clone https://huggingface.co/spaces/SoSa123456/clinic-lead-agent clinic-lead-agent-space
cp -R /path/to/extracted/clinic-lead-agent/. clinic-lead-agent-space/
cd clinic-lead-agent-space
git add -A
git commit -m "Deploy Clinic Signal"
git push origin main
```

If Git asks for credentials:

- Username: `SoSa123456`
- Password: your `hf_...` WRITE token

Prefer `hf auth login` so the token is not placed in command history.

## Method 2 — Windows PowerShell

Install prerequisites:

```powershell
winget install --id Git.Git -e
py -m pip install --user --upgrade huggingface_hub
hf auth login
```

From the extracted project folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\upload_huggingface.ps1
```

Manual PowerShell method:

```powershell
git clone https://huggingface.co/spaces/SoSa123456/clinic-lead-agent clinic-lead-agent-space
Copy-Item "C:\path\to\clinic-lead-agent\*" ".\clinic-lead-agent-space" -Recurse -Force
Set-Location .\clinic-lead-agent-space
git add -A
git commit -m "Deploy Clinic Signal"
git push origin main
```

## Method 3 — Hugging Face CLI upload

This method does not use Git directly:

```bash
python -m pip install --upgrade huggingface_hub
hf auth login
hf upload SoSa123456/clinic-lead-agent . . --repo-type space
```

Run it from inside the extracted `clinic-lead-agent` directory.

## Space variables and secrets

In Space → Settings → Variables and secrets, add variables:

```text
SEND_ENABLED=false
DRY_RUN=true
PUBLIC_BASE_URL=https://sosa123456-clinic-lead-agent.hf.space
PDF_LINK_TTL_SECONDS=86400
PDF_LINK_LIMIT=100
```

Add secrets as needed:

```text
GEMINI_API_KEY1
GEMINI_API_KEY2
GEMINI_API_KEY3
BRAVE_SEARCH_API_KEY
WHATSAPP_TOKEN
WHATSAPP_PHONE_NUMBER_ID
TELEGRAM_BOT_TOKEN
BALE_BOT_TOKEN
RUBIKA_BOT_TOKEN
EITAA_APP_TOKEN
```

Keep `DRY_RUN=true` until every provider has been tested.

## Verify

After the Docker build finishes, open:

```text
https://sosa123456-clinic-lead-agent.hf.space
https://sosa123456-clinic-lead-agent.hf.space/api/health
```

Expected health response:

```json
{"ok": true, "service": "Clinic Signal", "mode": "live-audit-and-messaging"}
```
