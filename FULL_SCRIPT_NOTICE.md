# Full Script Notice

## Purpose
This package provides a full, reproducible coffee-price forecasting workflow for:

- Arabica monthly forecasting (main task)
- Robusta descriptive comparison (overlap period only)
- Exporting PowerBI-ready output tables

## Main Script
- `coffee_forecasting_pipeline.py`

## One-Click Runner
- `run_pipeline.bat`

What the BAT file does:
1. Creates `.venv` (if missing)
2. Installs dependencies from `requirements.txt`
3. Runs `coffee_forecasting_pipeline.py`
4. If `outputs\` is locked, re-runs automatically into `outputs_retry\`
5. Opens the active output folder for immediate PowerBI connection
5. Attempts to launch Power BI Desktop (default install path)

## Python Dependencies
- Listed in `requirements.txt`

## Required Input Data Files (same folder as script)
- `Db_all_commodities.xlsx`
- `ENSO.xlsx`
- `psd.xls`
- `WB_CCKP_PR_WIDEF.csv`

## Output Folder for PowerBI
- `outputs\`

Generated files:
- `arabica_monthly_actuals.csv`
- `arabica_forecasts.csv`
- `model_metrics.csv`
- `drivers_monthly.csv`
- `robusta_descriptive.csv`
- `garch_volatility.csv`
- `pipeline_checks.json`

## PowerBI Connection (after BAT run)
1. Open Power BI Desktop.
2. Select **Get Data** > **Text/CSV**.
3. Import each CSV from `outputs\`.
4. Create relationships on date/month fields as needed.
5. Build visuals (actual vs forecast, model metrics, drivers, robusta comparison).

## Important Runtime Note
If both primary and retry runs fail with `PermissionError`, close Excel/PowerBI tabs that currently hold output CSV files, then re-run `run_pipeline.bat`.
