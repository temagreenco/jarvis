@echo off
REM JARVIS Local Video Cutter - Windows Batch File
REM
REM Usage: run_local_cut.bat "E:\path\to\video.mp4" "E:\path\to\output"

setlocal EnableDelayedExpansion

REM Check arguments
if "%~1"=="" (
    echo Usage: run_local_cut.bat "input_video.mp4" "output_folder"
    echo.
    echo Example:
    echo   run_local_cut.bat "E:\Desktop\ny20msmall_1.mp4" "E:\Desktop\results"
    exit /b 1
)

set INPUT=%~1
set OUTPUT=%~2

if "%OUTPUT%"=="" set OUTPUT=.\results

echo ============================================================
echo JARVIS Local Video Cutter
echo ============================================================
echo Input:  %INPUT%
echo Output: %OUTPUT%
echo ============================================================

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+
    exit /b 1
)

REM Check for FFmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo ERROR: FFmpeg not found. Please install FFmpeg and add to PATH
    exit /b 1
)

REM Run the local cutter
python local_cut.py "%INPUT%" "%OUTPUT%" --language he --max-clips 5 --target-duration 30 --mode accurate

echo.
echo Done! Check the output folder: %OUTPUT%
pause
