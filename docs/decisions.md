# Decisions

Recovered reference material that used to live in an untracked `CLAUDE.md`.
Covers the target transform call, the paint-seed/pattern lookup rationale, and
the project's architecture. Source of truth for anything the README or
notebooks point here for.

## Target transform decision

This comes from `notebooks/01_target_eda.ipynb`, run on the July 2026 data
(230,694 sales). **Both targets use `log()`.**

- **Apex filter.** Rows where either ratio is above 10 are dropped
  (`APEX_THRESHOLD` in `src/features/build_features.py`). That removed 2,499 rows,
  about 1.1% of the data, mostly Tier 1 blue gems, max-red Kimonos and iBP Howls.
  Before the filter, both ratios had max ≈ 86,000 and skew ≈ 200.
- **The log rule fires even after filtering.** Skew is about 5 and max/median is 10,
  so the tail is multiplicative.

| Stat (after filter, n = 228,195) | B: `price / ref_base_price` | C: `price / ref_predicted_price` |
|---|---:|---:|
| p25 / median / p75 | 0.949 / 1.000 / 1.135 | 0.954 / 1.000 / 1.084 |
| mean / std | 1.238 / 0.813 | 1.209 / 0.783 |
| skew / kurtosis | 5.05 / 34.5 | 5.28 / 37.6 |

Model C's IQR is narrower because `ref_predicted_price` already includes the
float factor, which leaves less residual variance.

## Pattern lookup rationale

`paint_seed` is an ID, not a magnitude — do not feed it as a raw int. For
Case Hardened and Fade/Doppler finishes, the relationship between seed and
price premium is a lookup, not a learnable function of the integer:

- **Fade % and Blue Gem percentages are returned by CSFloat directly** in
  `item.fade.{percentage, rank}` and `item.blue_gem.{playside_*, backside_*}`
  — use those, don't recompute them.
- For everything else, map `paint_seed` via a lookup table: `doppler_phase`
  (categorical: P1–4, Ruby, Sapphire, Black Pearl, Emerald), `is_blue_gem`,
  `seed_tier` (1, 2, 3, or none), Marble Fade Fire & Ice / Red Tip, Crimson Web
  hot-spots, Slaughter / Tiger Tooth patterns.
- For Case Hardened: AK #661 ("Scar") is its own tier. Tier 1 AK seeds include
  151, 179, 321, 387, 670, 955. ~7% of seeds are any blue gem.
- There's no good single API for these tiers — the plan is to build a local
  table: Case Hardened blue% from CSBlueGem / isitabluegem, fade % (80/90/95/100)
  per-weapon fade tables, Doppler phases via seed-keyed tables per knife type,
  Marble Fade / Crimson Web / Slaughter / Tiger Tooth likewise. Baked into
  `data/static/patterns.parquet` keyed by `(def_index, paint_index, paint_seed)`.
  Don't try to learn these from raw `paint_seed` as an integer — the
  relationship is a lookup, not a function. (`02_feature_eda.ipynb` confirms
  empirically: `paint_seed` has 1,001 unique values, consistent with needing
  the lookup table rather than being fed as a raw int.)

## Architecture notes

### Three models in parallel (not stages)

`ref_base_price` and `ref_predicted_price` come straight off each CSFloat sale
row (`reference.base_price`, `reference.predicted_price`) — there's no
separate Skinport-median computation.

- **Model A — Ridge/GAM baseline** on `price / ref_base_price`. Sanity check.
- **Model B — CatBoost** on `price / ref_base_price`. Classical overprice model.
- **Model C — CatBoost** on `price / ref_predicted_price`. `ref_predicted_price`
  is CSFloat's own Float Appraiser output. Model C learns the **residual
  against the public Float Appraiser** — what CSFloat misses on
  pattern/sticker overpay. This is the one productionized for weekly
  retraining.
- Split is always **temporal** (train on older snapshots, test on newer) —
  random splits leak future price information.

### Actual project structure

The layout diverged from the original proposal (no `data/` tree, no
`enrich/`, no per-model files under `src/models/` — the models themselves
live only in `notebooks/03_train.ipynb`, not yet promoted to `src/`):

```
.
├── README.md, docs/decisions.md
├── .env, .env_example
├── docker-compose.yml             # Airflow + Postgres + ClickHouse — only
│                                   # the ClickHouse service is actually run from here
├── requirements.txt
├── config/                        # batch_0..13_skins.yaml — ~6,900 skins for the ingest DAG
├── sql/
│   ├── 001_csfloat_sales.sql          # CREATE TABLE csfloat_sales (ReplacingMergeTree)
│   ├── 002_csfloat_listings.sql
│   ├── 003_csfloat_feature_eng.sql    # the SELECT build_features() consumes
│   └── 004_csfloat_sales_eda.sql
├── src/
│   ├── ingest/         csfloat_client.py, csfloat_schemas.py (pydantic schema-drift guard), clickhouse_loader.py
│   ├── features/       build_features.py, temporal_split.py
│   └── models/         eval.py (rmse_log, mdape_backtransformed) — no model classes here, see above
├── dags/                           # csfloat_ingest_dag.py — see "Where the pipeline actually runs", this copy isn't what runs
├── notebooks/
│   ├── 01_target_eda.ipynb         # -> log transform decision (see "Target transform decision")
│   ├── 02_feature_eda.ipynb        # -> feature set decisions
│   └── 03_train.ipynb              # Models A/B/C, trained and compared
└── tests/
    └── test_schema_drift.py        # fails loudly if CSFloat changes the sales-history payload
```

### Where the pipeline actually runs

This repo's own `docker-compose.yml` defines a full Airflow + Postgres + ClickHouse
stack, but **in practice only the ClickHouse service from it runs**
(`item_factor_est-clickhouse-1`; alias `clickhouse_csfloat_ingest_host` on the
external network `item_factor_est_default`). The DAGs actually execute in a
separate Airflow project:

- **`/home/aidar/projects/airflow`** runs `csfloat_ingest_dag.py` (daily ingest —
  the copy at `dags/csfloat_ingest_dag.py` in *this* repo is kept identical by
  hand, it is not deployed from here) and `csfloat_model_retrain_dag.py`
  (weekly): pulls the `csfloat_sales` slice ingested up to the run's cutoff,
  runs Optuna HPO on CatBoost (Model C's search space, ported from
  `03_train.ipynb`), scores the new model and the current registered champion
  on the same temporal test slice, and — only if the new model wins — registers
  it with the `champion` alias along with the exact SQL that produced its
  training slice. That project's `src/features/build_features.py`
  and `src/features/temporal_split.py` are **copies** of the ones in this
  repo — if you change feature engineering here, copy the change there too, or
  the two will silently diverge.
- **`/home/aidar/projects/mlflow`** is the MLflow tracking server (Postgres
  backend, MinIO artifact store) that retrain run logs to — UI at
  http://localhost:5000. The registered model is `csfloat_model_c`.

Local ports: ClickHouse HTTP is `localhost:8023` and native is `localhost:9000`.
The unused Airflow in this compose file would be on `localhost:8088`. The shared
Airflow is at `localhost:8080`.

If asked to change how Model C trains, retrains, or is evaluated, the work
almost certainly belongs in the `airflow` project, not here — this repo is
upstream of it (data + notebooks + the original feature/eval code it was
ported from), not a duplicate of it.
