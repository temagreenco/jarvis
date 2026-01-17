# JARVIS SaaS Backend (Docker Compose)

## Quick start (PowerShell)
```powershell
Copy-Item .env.example .env
docker compose up -d --build
.\scripts\create_minio_buckets.ps1
```

## Quick start (bash)
```bash
cp .env.example .env
docker compose up -d --build
./scripts/create_minio_buckets.sh
```

## Ensure bucket is private (if it was public before)
```powershell
$mcHostLocal = "http://$Env:MINIO_ROOT_USER`:$Env:MINIO_ROOT_PASSWORD@minio:9000"
docker compose run --rm -e MC_HOST_local=$mcHostLocal minio-mc anonymous set none "local/$Env:MINIO_BUCKET"
```

## GPU worker (optional)
```bash
docker compose --profile gpu up -d --build
```

## API usage
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"source_url":"s3://bucket/input.mp4","metadata":{"client":"acme"}}'

curl http://localhost:8000/jobs/<job_id>
```

## Smoke test (presigned download)
```powershell
.\scripts\smoke_fetch_result.ps1 -JobId <job_id>
```

## Cut job test (upload + submit)
```powershell
.\scripts\submit_cut_job.ps1 -InputPath C:\path\to\sample.mp4
.\scripts\submit_cut_job.ps1 -InputPath C:\path\to\sample.mp4 -SnapToSilence $true -SnapWindowSec 1.0
```

## Auto clips test (transcribe + select + cut)
```powershell
.\scripts\submit_auto_clips_job.ps1 -InputPath C:\path\to\sample.mp4
.\scripts\submit_auto_clips_job.ps1 -InputPath C:\path\to\sample.mp4 -SnapToSilence $false
```

## Auto clips notes
- Requires `faster-whisper` (installed in Docker image).
- Default model uses `JARVIS_WHISPER_MODEL` (e.g., `base`, `small`, `medium`, `large-v3`).

## Snap to silence
- `snap_to_silence` uses FFmpeg silencedetect to adjust segment boundaries.
- Defaults: enabled for `auto_clips`, disabled for `cut` unless explicitly set.
- A/B test by running the same job with `-SnapToSilence $true` and `$false`.

## Presigned URL TTL
```bash
PRESIGN_EXPIRES_SECONDS=3600
```

## Presigned URL host
```bash
MINIO_PUBLIC_ENDPOINT=http://localhost:9000
```

## Useful commands
```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker_cpu
```
