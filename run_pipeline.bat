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
if not exist ".tmp" mkdir ".tmp"
set "TEMP=%cd%\.tmp"
set "TMP=%cd%\.tmp"

echo.
echo [1/6] Checking Python installation...
set "PYTHON_CMD="

REM Prefer Python Launcher (py) because it works even when python.exe is not on PATH.
where py >nul 2>&1
if not errorlevel 1 (
  py -3.13 --version >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=py -3.13"
)
if not defined PYTHON_CMD (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3.12 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3.12"
  )
)
if not defined PYTHON_CMD (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3.11 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3.11"
  )
)

REM Fallback to python.exe on PATH.
if not defined PYTHON_CMD (
  where python >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if defined PYTHON_CMD (
  %PYTHON_CMD% --version >nul 2>&1
  if errorlevel 1 set "PYTHON_CMD="
)

REM Fallback to common per-user install locations without hardcoding username.
if not defined PYTHON_CMD (
  if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python313\python.exe""
)
if not defined PYTHON_CMD (
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
)
if not defined PYTHON_CMD (
  if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python311\python.exe""
)
if not defined PYTHON_CMD (
  echo ERROR: Python is not available for this shell session.
  echo Please install Python 3.11+ and re-run this file.
  exit /b 1
)

echo.
echo [2/6] Creating virtual environment (.venv) if needed...
if not exist ".venv\Scripts\python.exe" (
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    exit /b 1
  )
)

echo.
echo [3/6] Preparing virtual environment tools...
set "VENV_PY=.venv\Scripts\python.exe"
set "RUN_PY=%PYTHON_CMD%"
set "PIP_USER="
if exist "%VENV_PY%" (
  set "RUN_PY=%VENV_PY%"
  set "PIP_USER="
  "%VENV_PY%" -m ensurepip --upgrade >nul 2>&1
  if errorlevel 1 (
    echo WARNING: Could not bootstrap pip in .venv. Falling back to system Python.
    set "RUN_PY=%PYTHON_CMD%"
    set "PIP_USER="
  )
)

echo.
echo [4/6] Installing/updating requirements...
%RUN_PY% -m pip install --upgrade pip %PIP_USER%
%RUN_PY% -m pip install -r requirements.txt %PIP_USER%
if errorlevel 1 (
  echo ERROR: Failed to install dependencies from requirements.txt.
  exit /b 1
)

echo.
echo [5/6] Running forecasting pipeline...
if not exist "inputs\" (
  echo ERROR: Missing required folder: inputs\
  echo Create inputs\ and place all required source files inside it.
  exit /b 1
)
if not exist "inputs\Db_all_commodities.xlsx" (
  echo ERROR: Missing inputs\Db_all_commodities.xlsx
  exit /b 1
)
if not exist "inputs\ENSO.xlsx" (
  echo ERROR: Missing inputs\ENSO.xlsx
  exit /b 1
)
if not exist "inputs\psd.xls" (
  echo ERROR: Missing inputs\psd.xls
  exit /b 1
)
if not exist "inputs\WB_CCKP_PR_WIDEF.csv" (
  echo ERROR: Missing inputs\WB_CCKP_PR_WIDEF.csv
  exit /b 1
)
set "OUT_DIR=outputs"
set "COFFEE_OUT_DIR=%OUT_DIR%"
%RUN_PY% coffee_forecasting_pipeline.py
if errorlevel 1 (
  echo Primary run failed. Trying fallback output folder...
  set "OUT_DIR=outputs_retry"
  set "COFFEE_OUT_DIR=%OUT_DIR%"
  %RUN_PY% coffee_forecasting_pipeline.py
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
if not exist "%PBI_EXE%" set "PBI_EXE=%ProgramFiles(x86)%\Microsoft Power BI Desktop\bin\PBIDesktop.exe"
if not exist "%PBI_EXE%" (
  for /f "delims=" %%I in ('where PBIDesktop.exe 2^>nul') do (
    set "PBI_EXE=%%I"
    goto :PBI_FOUND
  )
)
:PBI_FOUND
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
