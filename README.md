# CS2 Skin Overprice Predictor

Predicts the **price multiplier** a CS2 skin listing sells for over its baseline
market price — the overpay driven by float value, paint seed (blue gems, fades,
Doppler phases), applied stickers, and keychains.

This is a personal / portfolio project, not a production service.

## How it works

1. **Ingest.** A daily job pulls CSFloat's undocumented `/history/{name}/sales`
   endpoint for a rotating batch of ~6,900 skins and writes cleared sales into
   ClickHouse (`default.csfloat_sales`).
2. **Feature engineering.** `src/features/build_features.py` turns raw sale rows
   into model-ready features: float position within its wear bucket, sticker
   value aggregation, fade/blue-gem percentages (CSFloat computes these for us),
   keychain price.
3. **Modeling.** Three models predict `log(price / baseline)`, evaluated with a
   **temporal split** (train on older sales, test on newer — random splits leak
   future price information):
   - **Model A** — Ridge/GAM baseline on `price / ref_base_price`.
   - **Model B** — CatBoost on `price / ref_base_price`.
   - **Model C** — CatBoost on `price / ref_predicted_price`, i.e. the residual
     against [CSFloat's own Float Appraiser](https://blog.csfloat.com/introducing-the-float-appraiser/).
     This is the headline model: it measures what CSFloat's public appraiser
     misses on pattern/sticker overpay.
4. **Retraining.** Model C is retrained weekly with Optuna hyperparameter search
   and tracked in MLflow, with a champion/challenger gate so a new model only
   replaces the last one if it actually tests better. **This pipeline lives in a
   separate project** — see [Related projects](#related-projects) below.

## Results (from `notebooks/03_train.ipynb`)

Both targets are log-transformed (see `docs/target_choice.md` for why). Trivial
baseline = trusting the denominator at face value (predict 0 in log-space).

| Model | Target | RMSE (log) | MAPE (back-transformed) |
|-------|--------|-----------:|-------------------------:|
| Trivial baseline | — | 0.3945 | 6.90% |
| Model B | `price / ref_base_price` | 0.2707 | 9.38% |
| Model C | `price / ref_predicted_price` | 0.2703 | 7.95% |

Model C beats the trivial "trust CSFloat" baseline on RMSE, i.e. there's
learnable residual signal CSFloat's public appraiser doesn't capture — see
`notebooks/02_feature_eda.ipynb` for which features carry that signal
(`sticker_to_base_ratio` and `float_position_in_bucket` are the strongest).

## Project layout

```
sql/                CREATE TABLE + feature-engineering SELECT for ClickHouse
src/
  ingest/            CSFloat client, pydantic schemas (schema-drift guard), ClickHouse loader
  features/          build_features(), temporal_split()
  models/            eval.py — rmse_log(), mdape_backtransformed()
dags/                Airflow DAG definitions (see note below — not what actually runs)
config/              batch_0..13_skins.yaml — the ~6,900 skins the ingest job cycles through
notebooks/
  01_target_eda.ipynb    target distribution analysis -> log-transform decision
  02_feature_eda.ipynb   feature distributions, correlations -> feature set
  03_train.ipynb         Models A/B/C training + comparison
docs/
  target_choice.md      log-vs-raw decision with full distribution stats
  status.md             point-in-time project status snapshot
tests/
  test_schema_drift.py   fails loudly if CSFloat changes the sales-history response shape
```

## Running it

This repo's `docker-compose.yml` defines Airflow + Postgres + ClickHouse, but in
practice **only the ClickHouse container from this compose file is actually
running** (`item_factor_est-clickhouse-1`) — the ingest DAG itself runs from a
separate Airflow project that reaches into this ClickHouse over an external
Docker network. See [Related projects](#related-projects).

```bash
# Bring up ClickHouse (and, if you want them, this repo's own unused Airflow services)
docker compose up -d clickhouse

# ClickHouse HTTP: localhost:8023, native: localhost:9000

# Notebooks: activate the ML venv and run Jupyter
source ~/study/bin/activate
jupyter notebook notebooks/
```

`.env.example` lists the required secrets (CSFloat API key, ClickHouse creds,
Airflow admin creds if you do run this repo's own Airflow stack).

## Related projects

- **`/home/aidar/projects/airflow`** — the Airflow instance that actually runs
  `csfloat_ingest_dag.py` (identical copy of `dags/csfloat_ingest_dag.py` here)
  and `csfloat_model_retrain_dag.py`, the weekly Model C retrain: Optuna HPO,
  MLflow tracking, and a champion/challenger gate that only promotes a new model
  if it beats the current one on a fresh temporal test slice. It reaches this
  repo's ClickHouse via the external Docker network `item_factor_est_default`
  (alias `clickhouse_csfloat_ingest_host`). `src/features/build_features.py` and
  `temporal_split.py` are copied there — **if you change them here, copy the
  change over too**, they will otherwise silently drift apart.
- **`/home/aidar/projects/mlflow`** — the MLflow tracking server + model
  registry (Postgres backend, MinIO artifact store) that the retrain DAG logs
  to. UI at http://localhost:5000.

See `CLAUDE.md` for full architectural context, data source details, and
feature engineering notes.
