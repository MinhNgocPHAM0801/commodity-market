@echo off
setlocal

REM ============================================================================
REM Coffee Forecasting Pipeline Runner
REM This script:
REM   1) Moves to the project folder
REM   2) Creates a local virtual environment (.venv) if missing
REM   3) Installs required packages from requirements.txt
REM   4) Runs coffee_forecasting_pipeline.py
REM   5) Opens the output folder for PowerBI import
REM   6) Tries to launch Power BI Desktop (if installed in default location)
REM ============================================================================

REM Project root is the folder where this BAT file exists
cd /d "%~dp0"

echo.
echo [1/6] Checking Python installation...
where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python is not found in PATH.
  echo Please install Python 3.11+ and re-run this file.
  exit /b 1
)

echo.
echo [2/6] Creating virtual environment (.venv) if needed...
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    exit /b 1
  )
)

echo.
echo [3/6] Activating virtual environment...
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo ERROR: Failed to activate virtual environment.
  exit /b 1
)

echo.
echo [4/6] Installing/updating requirements...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: Failed to install dependencies from requirements.txt.
  exit /b 1
)

echo.
echo [5/6] Running forecasting pipeline...
set "OUT_DIR=outputs"
set "COFFEE_OUT_DIR=%OUT_DIR%"
python coffee_forecasting_pipeline.py
if errorlevel 1 (
  echo Primary run failed. Trying fallback output folder...
  set "OUT_DIR=outputs_retry"
  set "COFFEE_OUT_DIR=%OUT_DIR%"
  python coffee_forecasting_pipeline.py
  if errorlevel 1 (
    echo ERROR: Pipeline run failed.
    echo If CSV files are open in Excel/PowerBI, close them and run again.
    exit /b 1
  )
)

echo.
echo [6/6] Opening output folder for PowerBI import...
if not exist "%OUT_DIR%" (
  echo ERROR: %OUT_DIR% folder was not created.
  exit /b 1
)
start "" explorer "%cd%\%OUT_DIR%"

REM Optional: auto-launch Power BI Desktop if found in default install location
set "PBI_EXE=%ProgramFiles%\Microsoft Power BI Desktop\bin\PBIDesktop.exe"
if exist "%PBI_EXE%" (
  echo Launching Power BI Desktop...
  start "" "%PBI_EXE%"
) else (
  echo Power BI Desktop executable not found at default path.
  echo Open Power BI manually, then import CSV files from:
  echo   %cd%\%OUT_DIR%
)

echo.
echo Done. You can now connect PowerBI to files in the outputs folder.
exit /b 0
