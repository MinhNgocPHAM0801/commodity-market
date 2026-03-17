# Coffee Forecasting Pipeline

This repository provides a full, reproducible coffee-price forecasting workflow for:

- Arabica monthly forecasting (main task)
- Robusta descriptive comparison (overlap period only)
- Power BI-ready output tables

## Main Files
- `coffee_forecasting_pipeline.py` (main script)
- `run_pipeline.bat` (one-click runner)
- `requirements.txt` (Python dependencies)

## Required Input Data Files
Keep these files inside the `inputs/` folder:

- `inputs/Db_all_commodities.xlsx`
- `inputs/ENSO.xlsx`
- `inputs/psd.xls`
- `inputs/WB_CCKP_PR_WIDEF.csv`

## One-Click Run
Run the pipeline with:

```bash
python coffee_forecasting_pipeline.py
```

Or use:

```bat
run_pipeline.bat
```

What `run_pipeline.bat` does:
1. Creates `.venv` (if missing)
2. Installs dependencies from `requirements.txt`
3. Runs `coffee_forecasting_pipeline.py`
4. If `outputs\` is locked, re-runs automatically into `outputs_retry\`
5. Opens the active output folder for immediate Power BI use
6. Attempts to launch Power BI Desktop (default install path)

## Outputs
Primary output folder:
- `outputs\`

Generated files:
- `arabica_monthly_actuals.csv`
- `arabica_forecasts.csv`
- `model_metrics.csv`
- `drivers_monthly.csv`
- `robusta_descriptive.csv`
- `garch_volatility.csv`
- `pipeline_checks.json`

## Modeling Notes
- Train window: `2000-01` to `2023-12`
- Out-of-sample backtest: `2024-01` to `2026-01`
- Forecast horizon: next month + 12-month path
- If `xgboost` is unavailable, ML model falls back to `GradientBoostingRegressor`

## Power BI Setup Guide
Use this once after running `run_pipeline.bat` (or the Python script):

1. Open Power BI Desktop.
2. Select **Get Data** > **Text/CSV**.
3. Import CSV files from `outputs\`:
   - `arabica_monthly_actuals.csv`
   - `arabica_forecasts.csv`
   - `model_metrics.csv`
   - `drivers_monthly.csv`
   - `robusta_descriptive.csv`
   - `garch_volatility.csv`
4. In **Model** view, create relationships on the shared month/date fields.
5. Build visuals (actual vs forecast, model metrics, drivers, robusta comparison).
6. On future updates, just refresh data after re-running the pipeline.

## Runtime Note
If both primary and retry runs fail with `PermissionError`, close Excel/Power BI tabs currently holding output CSV files, then re-run `run_pipeline.bat`.
