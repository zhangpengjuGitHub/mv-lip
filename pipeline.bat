@echo off
setlocal
set "MV_PY=C:\Python311\python.exe"
set "FFMPEG=%~dp0..\music-mv\tools\ffmpeg.exe"
if not exist "%FFMPEG%" set "FFMPEG=ffmpeg"
echo.
echo  ===== mv-lip pipeline =====
echo   1 = PREPARE  (extract audio + demucs dry vocal + 25fps video)
echo   2 = FINISH   (mux original mix + QC sheet)
echo.
set /p CH="choose 1 or 2: "
if "%CH%"=="1" goto prep
if "%CH%"=="2" goto finish
echo bad choice
goto end
:prep
"%MV_PY%" "%~dp0scripts\prep.py"
goto end
:finish
"%MV_PY%" "%~dp0scripts\finish.py"
goto end
:end
echo.
pause
