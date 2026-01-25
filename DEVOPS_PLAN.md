# DevOps Plan for Jarvis

## Workflow
1. **Task**: User defines a task.
2. **Plan**: Assistant creates a plan (updates `FIX_PLAN.md` or similar).
3. **Edit**: Assistant edits code.
4. **Verify**: User runs tests/docker (Assistant provides commands).
5. **Commit**: User commits changes.

## Commands
- **Start**: `docker compose up -d`
- **Logs**: `docker compose logs -f api`
- **Clip Test**: `.\scripts\submit_auto_clips_job.ps1`
