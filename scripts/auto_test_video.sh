#!/bin/bash
# JARVIS Video Editor - Automated Test & Fix Loop
# Usage: ./scripts/auto_test_video.sh [video_file]

VIDEO_FILE="${1:-videos/test.mp4}"
MAX_ATTEMPTS=5
LOG_FILE="output/test_run_$(date +%Y%m%d_%H%M%S).log"

echo "=== JARVIS Video Editor Auto-Test ===" | tee "$LOG_FILE"
echo "Video: $VIDEO_FILE" | tee -a "$LOG_FILE"
echo "Max attempts: $MAX_ATTEMPTS" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

for i in $(seq 1 $MAX_ATTEMPTS); do
    echo "=== Attempt $i/$MAX_ATTEMPTS ===" | tee -a "$LOG_FILE"

    # Run video processing
    if python -m jarvis video process "$VIDEO_FILE" 2>&1 | tee -a "$LOG_FILE"; then
        echo "" | tee -a "$LOG_FILE"
        echo "✓ SUCCESS! Reels generated in output/" | tee -a "$LOG_FILE"

        # List generated files
        echo "Generated files:" | tee -a "$LOG_FILE"
        ls -la output/reel_*.mp4 2>/dev/null | tee -a "$LOG_FILE"
        exit 0
    fi

    echo "" | tee -a "$LOG_FILE"
    echo "✗ Failed. Asking Claude to fix..." | tee -a "$LOG_FILE"

    # Extract last error
    ERROR=$(tail -50 "$LOG_FILE" | grep -i "error\|exception\|failed" | tail -5)

    # Ask Claude to fix (non-interactive)
    claude -p "The video processing failed with this error:
$ERROR

Check modules/video_editor.py and fix the issue. Then confirm the fix." 2>&1 | tee -a "$LOG_FILE"

    echo "" | tee -a "$LOG_FILE"
    sleep 2
done

echo "=== Max attempts reached ===" | tee -a "$LOG_FILE"
echo "Check $LOG_FILE for details" | tee -a "$LOG_FILE"
exit 1
