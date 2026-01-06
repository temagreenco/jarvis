# CLAUDE.md - Working Guidelines

## Communication Rules

### 1. Share Error Output Directly
```powershell
# Copy full error with context
python cli.py process --video test.mp4 2>&1 | clip
# Then paste it
```

### 2. Be Specific About What You Want
| Instead of | Say |
|------------|-----|
| "fix the video editor" | "FFmpeg fails on Hebrew subtitles on Windows" |
| "make it better" | "add retry logic to the API calls" |
| "it's broken" | paste error + what you expected |

### 3. Environment Context
```
OS: Windows 11
Python: 3.11
FFmpeg: (check with ffmpeg -version)
GPU: Your GPU model
Docker: Installed
```

### 4. Short Iterative Requests
```
Good:
1. "add face detection" → implement
2. "now add caching" → extend
3. "it's slow" → optimize

Avoid:
"add face detection with caching and make it fast and add tests and..."
```

### 5. Point to Relevant Files
```
Good: "bug is in modules/video_editor.py around line 350"
Slow: "something's wrong with the video code"
```

### 6. Ask for Plans on Big Changes
```
"Plan how to add web UI to JARVIS"
→ I outline approach before coding
```

### 7. Tell Me What NOT to Change
```
"Fix subtitle rendering but don't touch zoom logic"
```

### 8. Request Parallel Work
```
"In parallel: add tests for video_editor AND update README"
→ I launch multiple agents simultaneously
```

### 9. Paste Terminal Output
Full PowerShell sessions are perfect - shows:
- Commands you ran
- Exact errors
- Your environment

---

## Project Context

### Local Paths (Windows)
- Project: `F:\dev\jarvis`
- Videos: `F:\dev\jarvis\data\downloads\`
- Output: `F:\dev\jarvis\output\`

### Docker
- Username: `temagreen`
- Image: `temagreen/jarvis-gpu:latest`

### RunPod (Cloud)
- Endpoint: (set after deployment)
- API Key: (set after deployment)

---

## Current Status
- FFmpeg: Not configured on Windows (use cloud)
- Cloud deployment: In progress
- Video editor: Ready (needs FFmpeg)

---

## VTSS Protocol
Every change must be:
1. **V**erify - Check it works
2. **T**est - Run tests
3. **S**ecure - No vulnerabilities
4. **S**peed - Optimize performance
