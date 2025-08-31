@echo off
REM ---- Add ffmpeg to PATH temporarily ----
set PATH=C:\Users\upans\OneDrive\Desktop\car\project\ffmpeg-8.0-essentials_build\bin;%PATH%

REM ---- Go to project folder ----
cd /d "C:\Users\upans\OneDrive\Desktop\car\project"

REM ---- Run backend ----
python app.py

pause
