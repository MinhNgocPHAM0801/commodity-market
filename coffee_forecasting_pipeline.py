from __future__ import annotations

import json
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from arch import arch_model
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "outputs"
OUT_DIR.mkdir(exist_ok=True)

COMMODITIES_FILE = BASE_DIR / "Db_all_commodities.xlsx"
ENSO_FILE = BASE_DIR / "ENSO.xlsx"
PSD_FILE = BASE_DIR / "psd.xls"
PRECIP_FILE = BASE_DIR / "WB_CCKP_PR_WIDEF.csv"

TRAIN_END = pd.Timestamp("2023-12-01")
TEST_START = pd.Timestamp("2024-01-01")
TEST_END = pd.Timestamp("2026-01-01")
FORECAST_HORIZON = 12


@dataclass
class ModelResult:
    model: str
    predictions: pd.Series
    low: pd.Series
    high: pd.Series


def sanitize_col(name: str) -> str:
    return (
        str(name)
        .lower()
        .replace("&", "and")
        .replace(".", "")
        .replace(",", "")
        .replace(" ", "_")
    )


def load_commodities() -> Tuple[pd.DataFrame, pd.DataFrame]:
    cols = [
        "date",
        "ticker",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "commodity",
        "robusta_close",
    ]
    df = pd.read_excel(COMMODITIES_FILE, header=None, names=cols)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()].copy()
    df = df.sort_values("date")

    arabica = df[["date", "open", "high", "low", "close", "volume"]].copy()
    robusta = df[df["robusta_close"].notna()][["date", "robusta_close"]].copy()
    return arabica, robusta


def arabica_to_monthly(arabica_daily: pd.DataFrame) -> pd.DataFrame:
    df = arabica_daily.copy()
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df["daily_return"] = df["close"].pct_change()

    monthly = (
        df.groupby("month", as_index=False)
        .agg(
            arabica_close=("close", "mean"),
            arabica_close_last=("close", "last"),
            arabica_open_mean=("open", "mean"),
            arabica_high_max=("high", "max"),
            arabica_low_min=("low", "min"),
            arabica_volume_sum=("volume", "sum"),
            arabica_realized_vol=("daily_return", "std"),
            trading_days=("date", "count"),
        )
        .sort_values("month")
    )
    monthly["arabica_realized_vol"] = monthly["arabica_realized_vol"].fillna(0.0)
    return monthly


def load_enso() -> pd.DataFrame:
    enso = pd.read_excel(ENSO_FILE)
    enso["month"] = pd.to_datetime(
        {"year": enso["YR"].astype(int), "month": enso["MON"].astype(int), "day": 1}
    )
    out = enso[
        ["month", "NINO1+2", "NINO3", "NINO4", "NINO3.4", "ANOM", "ANOM.1", "ANOM.2", "ANOM.3"]
    ].copy()
    out = out.rename(
        columns={
            "NINO1+2": "enso_nino12",
            "NINO3": "enso_nino3",
            "NINO4": "enso_nino4",
            "NINO3.4": "enso_nino34",
            "ANOM": "enso_anom12",
            "ANOM.1": "enso_anom3",
            "ANOM.2": "enso_anom4",
            "ANOM.3": "enso_anom34",
        }
    )
    return out.sort_values("month")


def load_psd_features() -> pd.DataFrame:
    psd = pd.read_html(PSD_FILE)[0]
    psd["Commodity"] = psd["Commodity"].ffill()
    psd["Attribute"] = psd["Attribute"].ffill()

    countries = {
        "Brazil",
        "Colombia",
        "Ethiopia",
        "Guatemala",
        "Honduras",
        "India",
        "Indonesia",
        "Peru",
        "Uganda",
        "Vietnam",
    }
    attrs = {
        "Arabica Production",
        "Robusta Production",
        "Beginning Stocks",
        "Ending Stocks",
        "Production",
        "Exports",
        "Imports",
        "Domestic Consumption",
        "Total Supply",
        "Total Distribution",
    }
    year_cols = [c for c in psd.columns if isinstance(c, str) and "/" in c and c[:4].isdigit()]

    df = psd[(psd["Country"].isin(countries)) & (psd["Attribute"].isin(attrs))].copy()
    long = df.melt(
        id_vars=["Attribute", "Country"],
        value_vars=year_cols,
        var_name="market_year",
        value_name="value",
    )
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long.dropna(subset=["value"])
    long["year"] = long["market_year"].str.split("/").str[1].astype(int)

    agg = (
        long.groupby(["year", "Attribute"], as_index=False)["value"]
        .sum()
        .pivot(index="year", columns="Attribute", values="value")
        .reset_index()
    )
    agg.columns = ["year"] + [f"psd_{sanitize_col(c)}" for c in agg.columns[1:]]
    return agg


def load_precip_features() -> pd.DataFrame:
    precip = pd.read_csv(PRECIP_FILE)
    years = [c for c in precip.columns if c.isdigit()]
    long = precip.melt(id_vars=["Country"], value_vars=years, var_name="year", value_name="precip_mm")
    long["year"] = long["year"].astype(int)
    long["precip_mm"] = pd.to_numeric(long["precip_mm"], errors="coerce")
    out = long.groupby("year", as_index=False)["precip_mm"].mean()
    out = out.rename(columns={"precip_mm": "precip_mean_mm_10c"})
    return out


def build_monthly_dataset() -> Tuple[pd.DataFrame, pd.DataFrame]:
    arabica_daily, robusta_daily = load_commodities()
    arabica_monthly = arabica_to_monthly(arabica_daily)
    enso = load_enso()
    psd = load_psd_features()
    precip = load_precip_features()

    annual = psd.merge(precip, on="year", how="left").sort_values("year")
    feature_cols = [c for c in annual.columns if c != "year"]
    annual_lag = annual.copy()
    annual_lag[feature_cols] = annual_lag[feature_cols].shift(1)

    monthly = arabica_monthly.merge(enso, on="month", how="left")
    monthly["year"] = monthly["month"].dt.year
    monthly = monthly.merge(annual_lag, on="year", how="left")
    monthly = monthly.sort_values("month")

    precip_col = "precip_mean_mm_10c"
    monthly[f"{precip_col}_carryforward_flag"] = monthly[precip_col].isna().astype(int)

    filled_cols = [c for c in feature_cols if c in monthly.columns]
    monthly[filled_cols] = monthly[filled_cols].ffill()
    monthly = monthly.drop(columns=["year"])

    robusta_monthly = robusta_daily.copy()
    robusta_monthly["month"] = robusta_monthly["date"].dt.to_period("M").dt.to_timestamp()
    robusta_monthly = (
        robusta_monthly.groupby("month", as_index=False)["robusta_close"].mean().sort_values("month")
    )

    spread = monthly[["month", "arabica_close"]].merge(robusta_monthly, on="month", how="inner")
    spread["arabica_robusta_ratio"] = spread["arabica_close"] / spread["robusta_close"]
    spread["arabica_minus_robusta"] = spread["arabica_close"] - spread["robusta_close"]

    return monthly, spread


def add_ml_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for lag in [1, 2, 3, 6, 12]:
        out[f"lag_{lag}"] = out["arabica_close"].shift(lag)
    for win in [3, 6, 12]:
        out[f"roll_mean_{win}"] = out["arabica_close"].shift(1).rolling(win).mean()
        out[f"roll_std_{win}"] = out["arabica_close"].shift(1).rolling(win).std()
    return out


def split_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    train = df[df["month"] <= TRAIN_END].copy()
    test = df[(df["month"] >= TEST_START) & (df["month"] <= TEST_END)].copy()
    return train, test


def safe_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = np.where(np.abs(y_true) < 1e-8, np.nan, np.abs(y_true))
    return float(np.nanmean(np.abs((y_true - y_pred) / denom)) * 100.0)


def directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) < 2:
        return float("nan")
    true_diff = np.sign(np.diff(y_true))
    pred_diff = np.sign(np.diff(y_pred))
    return float((true_diff == pred_diff).mean() * 100.0)


def metric_frame(y_true: pd.Series, preds: Dict[str, pd.Series], window: str) -> pd.DataFrame:
    rows = []
    y = y_true.values
    for name, p in preds.items():
        yp = p.reindex(y_true.index).values
        rows.append(
            {
                "model": name,
                "window": window,
                "mae": mean_absolute_error(y, yp),
                "rmse": math.sqrt(mean_squared_error(y, yp)),
                "mape": safe_mape(y, yp),
                "directional_accuracy": directional_accuracy(y, yp),
            }
        )
    return pd.DataFrame(rows).sort_values("mae")


def fit_predict_arima(train_y: pd.Series, forecast_x: pd.DataFrame | None = None) -> Tuple[float, float, float]:
    model = ARIMA(train_y, order=(1, 1, 1))
    fit = model.fit()
    fc = fit.get_forecast(steps=1)
    pred = float(fc.predicted_mean.iloc[0])
    ci = fc.conf_int(alpha=0.05).iloc[0]
    return pred, float(ci.iloc[0]), float(ci.iloc[1])


def fit_predict_sarima(train_y: pd.Series) -> Tuple[float, float, float]:
    model = SARIMAX(
        train_y,
        order=(1, 1, 1),
        seasonal_order=(1, 0, 1, 12),
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    fit = model.fit(disp=False)
    fc = fit.get_forecast(steps=1)
    pred = float(fc.predicted_mean.iloc[0])
    ci = fc.conf_int(alpha=0.05).iloc[0]
    return pred, float(ci.iloc[0]), float(ci.iloc[1])


def fit_predict_sarimax(train_y: pd.Series, train_x: pd.DataFrame, next_x: pd.DataFrame) -> Tuple[float, float, float]:
    tx = train_x.copy()
    ty = train_y.copy()
    valid = tx.replace([np.inf, -np.inf], np.nan).notna().all(axis=1) & ty.notna()
    tx = tx.loc[valid]
    ty = ty.loc[valid]
    if len(tx) < 24:
        return fit_predict_sarima(train_y)

    nx = next_x.copy().replace([np.inf, -np.inf], np.nan)
    for c in nx.columns:
        if pd.isna(nx.iloc[0][c]):
            nx.iloc[0, nx.columns.get_loc(c)] = tx[c].iloc[-1]

    model = SARIMAX(
        ty,
        exog=tx,
        order=(1, 1, 1),
        seasonal_order=(1, 0, 1, 12),
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    fit = model.fit(disp=False)
    fc = fit.get_forecast(steps=1, exog=nx)
    pred = float(fc.predicted_mean.iloc[0])
    ci = fc.conf_int(alpha=0.05).iloc[0]
    return pred, float(ci.iloc[0]), float(ci.iloc[1])


def fit_predict_ml(
    train_df: pd.DataFrame, pred_row: pd.Series, feature_cols: List[str], use_xgb: bool
) -> Tuple[float, float, float]:
    x_train = train_df[feature_cols]
    y_train = train_df["arabica_close"]
    x_next = pd.DataFrame([pred_row[feature_cols].values], columns=feature_cols)

    if use_xgb:
        from xgboost import XGBRegressor

        model = XGBRegressor(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
            objective="reg:squarederror",
        )
    else:
        model = GradientBoostingRegressor(random_state=42)

    model.fit(x_train, y_train)
    pred = float(model.predict(x_next)[0])
    residuals = y_train - model.predict(x_train)
    q_low, q_high = np.quantile(residuals, [0.025, 0.975])
    return pred, float(pred + q_low), float(pred + q_high)


def walk_forward_forecasts(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    data = df.copy().set_index("month")
    train, test = split_data(data.reset_index())
    train = train.set_index("month")
    test = test.set_index("month")

    exog_cols = [
        c
        for c in data.columns
        if c.startswith("enso_") or c.startswith("psd_") or c.startswith("precip_")
    ]
    ml_cols = [c for c in data.columns if c.startswith("lag_") or c.startswith("roll_")] + exog_cols

    use_xgb = False
    try:
        import xgboost  # noqa: F401

        use_xgb = True
    except Exception:
        use_xgb = False

    model_rows = []
    pred_store: Dict[str, List[float]] = {
        "seasonal_naive": [],
        "arima": [],
        "sarima": [],
        "sarimax": [],
        "xgboost" if use_xgb else "ml_gbr_fallback": [],
    }
    low_store = {k: [] for k in pred_store}
    high_store = {k: [] for k in pred_store}

    test_months = test.index.to_list()
    for m in test_months:
        hist = data.loc[: m - pd.offsets.MonthBegin(1)].copy()
        y_hist = hist["arabica_close"]
        row = data.loc[m]

        s_pred = float(hist["arabica_close"].shift(12).iloc[-1]) if len(hist) > 12 else float(hist["arabica_close"].iloc[-1])
        pred_store["seasonal_naive"].append(s_pred)
        low_store["seasonal_naive"].append(s_pred)
        high_store["seasonal_naive"].append(s_pred)

        a_pred, a_low, a_high = fit_predict_arima(y_hist)
        pred_store["arima"].append(a_pred)
        low_store["arima"].append(a_low)
        high_store["arima"].append(a_high)

        sa_pred, sa_low, sa_high = fit_predict_sarima(y_hist)
        pred_store["sarima"].append(sa_pred)
        low_store["sarima"].append(sa_low)
        high_store["sarima"].append(sa_high)

        x_hist = hist[exog_cols].astype(float)
        x_next = pd.DataFrame([row[exog_cols].astype(float).values], columns=exog_cols)
        sx_pred, sx_low, sx_high = fit_predict_sarimax(y_hist, x_hist, x_next)
        pred_store["sarimax"].append(sx_pred)
        low_store["sarimax"].append(sx_low)
        high_store["sarimax"].append(sx_high)

        ml_train = hist.dropna(subset=ml_cols + ["arabica_close"])
        if m in ml_train.index:
            ml_train = ml_train.drop(index=m, errors="ignore")
        if pd.notna(row[ml_cols]).all() and len(ml_train) > 36:
            ml_pred, ml_low, ml_high = fit_predict_ml(ml_train, row, ml_cols, use_xgb)
        else:
            ml_pred = sa_pred
            ml_low = sa_low
            ml_high = sa_high
        ml_name = "xgboost" if use_xgb else "ml_gbr_fallback"
        pred_store[ml_name].append(ml_pred)
        low_store[ml_name].append(ml_low)
        high_store[ml_name].append(ml_high)

    for model_name, values in pred_store.items():
        for i, m in enumerate(test_months):
            model_rows.append(
                {
                    "forecast_date": m.strftime("%Y-%m-%d"),
                    "target_month": m.strftime("%Y-%m-%d"),
                    "model": model_name,
                    "yhat": values[i],
                    "pi_low": low_store[model_name][i],
                    "pi_high": high_store[model_name][i],
                    "is_oos": 1,
                }
            )

    preds = {name: pd.Series(vals, index=test.index) for name, vals in pred_store.items()}
    metrics = metric_frame(test["arabica_close"], preds, window="2024-01_to_2026-01")
    return pd.DataFrame(model_rows), metrics


def garch_volatility(train_series: pd.Series, test_idx: pd.Index) -> pd.DataFrame:
    returns = np.log(train_series).diff().dropna() * 100.0
    model = arch_model(returns, vol="Garch", p=1, q=1, dist="normal", mean="Constant")
    fit = model.fit(disp="off")

    fc = fit.forecast(horizon=len(test_idx), reindex=False)
    var_fc = fc.variance.values[-1]
    vol_fc = np.sqrt(var_fc)
    out = pd.DataFrame({"month": test_idx, "garch_vol_forecast_pct": vol_fc})
    return out


def final_horizon_forecast(df: pd.DataFrame, best_model: str) -> pd.DataFrame:
    data = df.copy().set_index("month")
    data = data.sort_index()
    exog_cols = [
        c
        for c in data.columns
        if c.startswith("enso_") or c.startswith("psd_") or c.startswith("precip_")
    ]
    ml_cols = [c for c in data.columns if c.startswith("lag_") or c.startswith("roll_")] + exog_cols

    use_xgb = best_model == "xgboost"
    hist = data.copy()
    last_month = hist.index.max()
    rows = []

    for step in range(1, FORECAST_HORIZON + 1):
        target = (last_month + pd.offsets.MonthBegin(step)).replace(day=1)
        new_row = hist.iloc[-1].copy()
        new_row.name = target
        for lag in [1, 2, 3, 6, 12]:
            if len(hist) >= lag:
                new_row[f"lag_{lag}"] = hist["arabica_close"].iloc[-lag]
        for win in [3, 6, 12]:
            if len(hist) >= win:
                values = hist["arabica_close"].iloc[-win:]
                new_row[f"roll_mean_{win}"] = values.mean()
                new_row[f"roll_std_{win}"] = values.std()

        if best_model == "arima":
            pred, low, high = fit_predict_arima(hist["arabica_close"])
        elif best_model == "sarima":
            pred, low, high = fit_predict_sarima(hist["arabica_close"])
        elif best_model == "sarimax":
            x_hist = hist[exog_cols].astype(float)
            x_next = pd.DataFrame([new_row[exog_cols].astype(float).values], columns=exog_cols)
            pred, low, high = fit_predict_sarimax(hist["arabica_close"], x_hist, x_next)
        elif best_model in {"xgboost", "ml_gbr_fallback"}:
            train_ml = hist.dropna(subset=ml_cols + ["arabica_close"])
            if len(train_ml) > 24 and pd.notna(new_row[ml_cols]).all():
                pred, low, high = fit_predict_ml(train_ml, new_row, ml_cols, use_xgb=use_xgb)
            else:
                pred, low, high = fit_predict_sarima(hist["arabica_close"])
        else:
            pred = float(hist["arabica_close"].shift(12).iloc[-1]) if len(hist) > 12 else float(hist["arabica_close"].iloc[-1])
            low, high = pred, pred

        new_row["arabica_close"] = pred
        hist = pd.concat([hist, pd.DataFrame([new_row], index=[target])])
        rows.append(
            {
                "forecast_date": str(last_month.date()),
                "target_month": str(target.date()),
                "model": f"{best_model}_future_path",
                "yhat": pred,
                "pi_low": low,
                "pi_high": high,
                "is_oos": 0,
            }
        )
    return pd.DataFrame(rows)


def run_checks(monthly: pd.DataFrame, forecasts: pd.DataFrame) -> Dict[str, str]:
    checks = {}
    checks["monthly_dates_monotonic"] = str(monthly["month"].is_monotonic_increasing)
    checks["monthly_duplicate_dates"] = str(monthly["month"].duplicated().sum())
    checks["forecast_null_keys"] = str(
        forecasts[["forecast_date", "target_month", "model"]].isna().any().any()
    )
    checks["robusta_span_expected"] = "2024-07-26_to_2026-01-30"
    return checks


def main() -> None:
    monthly, robusta_desc = build_monthly_dataset()
    monthly = add_ml_features(monthly)
    monthly = monthly.sort_values("month")

    oos_forecasts, metrics = walk_forward_forecasts(monthly)

    train_data = monthly[monthly["month"] <= TRAIN_END].set_index("month")
    test_idx = monthly[(monthly["month"] >= TEST_START) & (monthly["month"] <= TEST_END)]["month"]
    garch = garch_volatility(train_data["arabica_close"], pd.Index(test_idx))

    best_model = metrics.iloc[0]["model"]
    future_path = final_horizon_forecast(monthly, best_model=best_model)
    all_forecasts = pd.concat([oos_forecasts, future_path], ignore_index=True)

    drivers = monthly[
        ["month"]
        + [c for c in monthly.columns if c.startswith("enso_") or c.startswith("psd_") or c.startswith("precip_")]
    ].copy()
    drivers = drivers.rename(columns={"month": "date"})

    arabica_actuals = monthly[
        ["month", "arabica_close", "arabica_realized_vol", "arabica_volume_sum", "trading_days"]
    ].copy()
    arabica_actuals = arabica_actuals.rename(columns={"month": "date"})

    robusta_out = robusta_desc.rename(columns={"month": "date"})

    arabica_actuals.to_csv(OUT_DIR / "arabica_monthly_actuals.csv", index=False)
    all_forecasts.to_csv(OUT_DIR / "arabica_forecasts.csv", index=False)
    metrics.to_csv(OUT_DIR / "model_metrics.csv", index=False)
    drivers.to_csv(OUT_DIR / "drivers_monthly.csv", index=False)
    robusta_out.to_csv(OUT_DIR / "robusta_descriptive.csv", index=False)
    garch.to_csv(OUT_DIR / "garch_volatility.csv", index=False)

    checks = run_checks(monthly, all_forecasts)
    checks["best_model"] = str(best_model)
    checks["ml_backend"] = "xgboost" if "xgboost" in metrics["model"].tolist() else "gradient_boosting_fallback"
    with open(OUT_DIR / "pipeline_checks.json", "w", encoding="utf-8") as f:
        json.dump(checks, f, indent=2)

    print("Pipeline complete.")
    print(f"Best model (OOS MAE): {best_model}")
    print(f"Outputs written to: {OUT_DIR}")


if __name__ == "__main__":
    main()
