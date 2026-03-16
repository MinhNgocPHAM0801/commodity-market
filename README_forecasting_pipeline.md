# Coffee Forecasting Pipeline

Run:

```bash
python coffee_forecasting_pipeline.py
```

The script reads:

- `Db_all_commodities.xlsx`
- `ENSO.xlsx`
- `psd.xls`
- `WB_CCKP_PR_WIDEF.csv`

Outputs are written to `outputs/`:

- `arabica_monthly_actuals.csv`
- `arabica_forecasts.csv`
- `model_metrics.csv`
- `drivers_monthly.csv`
- `robusta_descriptive.csv`
- `garch_volatility.csv`
- `pipeline_checks.json`

Notes:

- Train window: `2000-01` to `2023-12`
- Out-of-sample backtest: `2024-01` to `2026-01`
- Forecast horizon: next month + 12-month path
- If `xgboost` is unavailable, ML model falls back to `GradientBoostingRegressor`.
