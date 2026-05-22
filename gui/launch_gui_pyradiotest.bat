@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ================================================
echo  Radiomics Demo GUI Launcher
echo  Target conda environment: pyradiotest
echo ================================================
echo.

REM 1) If this BAT is launched inside an already-activated pyradiotest env, just run.
if /I "%CONDA_DEFAULT_ENV%"=="pyradiotest" (
    echo [OK] pyradiotest environment is already activated.
    python radiomics_demo_gui.py
    pause
    exit /b %ERRORLEVEL%
)

REM 2) If conda is already on PATH, use it.
where conda >nul 2>nul
if %ERRORLEVEL%==0 (
    echo [INFO] Found conda on PATH.
    call conda activate pyradiotest
    if not errorlevel 1 goto RUN_GUI
)

REM 3) Try common Anaconda/Miniconda locations.
set "CONDA_BAT="
for %%P in (
    "%USERPROFILE%\anaconda3\condabin\conda.bat"
    "%USERPROFILE%\miniconda3\condabin\conda.bat"
    "%USERPROFILE%\Anaconda3\condabin\conda.bat"
    "%USERPROFILE%\Miniconda3\condabin\conda.bat"
    "C:\ProgramData\anaconda3\condabin\conda.bat"
    "C:\ProgramData\Anaconda3\condabin\conda.bat"
    "C:\ProgramData\miniconda3\condabin\conda.bat"
    "C:\ProgramData\Miniconda3\condabin\conda.bat"
    "C:\Anaconda3\condabin\conda.bat"
    "C:\Miniconda3\condabin\conda.bat"
) do (
    if exist %%~P set "CONDA_BAT=%%~P"
)

if defined CONDA_BAT (
    echo [INFO] Found conda.bat:
    echo        !CONDA_BAT!
    call "!CONDA_BAT!" activate pyradiotest
    if not errorlevel 1 goto RUN_GUI
)

REM 4) Last fallback: directly call python.exe inside typical env paths.
set "ENV_PYTHON="
for %%P in (
    "%USERPROFILE%\anaconda3\envs\pyradiotest\python.exe"
    "%USERPROFILE%\miniconda3\envs\pyradiotest\python.exe"
    "%USERPROFILE%\Anaconda3\envs\pyradiotest\python.exe"
    "%USERPROFILE%\Miniconda3\envs\pyradiotest\python.exe"
    "C:\ProgramData\anaconda3\envs\pyradiotest\python.exe"
    "C:\ProgramData\Anaconda3\envs\pyradiotest\python.exe"
    "C:\ProgramData\miniconda3\envs\pyradiotest\python.exe"
    "C:\ProgramData\Miniconda3\envs\pyradiotest\python.exe"
) do (
    if exist %%~P set "ENV_PYTHON=%%~P"
)

if defined ENV_PYTHON (
    echo [INFO] conda command was not found, but pyradiotest python.exe was found:
    echo        !ENV_PYTHON!
    "!ENV_PYTHON!" radiomics_demo_gui.py
    pause
    exit /b %ERRORLEVEL%
)

echo [ERROR] Could not find conda or pyradiotest python.exe automatically.
echo.
echo Please use one of these methods:
echo   1. Open Anaconda Prompt, then run:
echo      conda activate pyradiotest
echo      cd /d "%~dp0"
echo      python radiomics_demo_gui.py
echo.
echo   2. Or check your conda installation folder and edit this BAT file.
echo.
pause
exit /b 1

:RUN_GUI
echo [OK] Conda environment activated: pyradiotest
echo.
python radiomics_demo_gui.py
pause
exit /b %ERRORLEVEL%
