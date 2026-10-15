"""
Unit tests for src/features/temporal_split.py and src/models/eval.py.

Fully offline — synthetic data only, no CSFloat API or ClickHouse calls.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest

from src.features.temporal_split import temporal_split
from src.models.eval import mdape_backtransformed, rmse_log


def _synthetic_sales(n: int) -> pl.DataFrame:
    """n rows with unique, evenly-spaced sold_at timestamps, shuffled so sort() is exercised."""
    start = datetime(2026, 1, 1)
    rows = [{"id": i, "sold_at": start + timedelta(hours=i)} for i in range(n)]
    rng = np.random.default_rng(seed=0)
    rng.shuffle(rows)
    return pl.DataFrame(rows)


def test_temporal_split_train_strictly_before_test():
    df = _synthetic_sales(100)
    df_train, df_test = temporal_split(df, date_col="sold_at", test_frac=0.2)

    assert df_train["sold_at"].max() < df_test["sold_at"].min()


def test_temporal_split_no_row_appears_in_both():
    df = _synthetic_sales(100)
    df_train, df_test = temporal_split(df, date_col="sold_at", test_frac=0.2)

    train_ids = set(df_train["id"].to_list())
    test_ids = set(df_test["id"].to_list())

    assert train_ids.isdisjoint(test_ids)
    assert train_ids | test_ids == set(range(100))


def test_temporal_split_sizes_match_requested_ratio():
    df = _synthetic_sales(100)
    df_train, df_test = temporal_split(df, date_col="sold_at", test_frac=0.2)

    assert len(df_train) == 80
    assert len(df_test) == 20


def test_rmse_log_zero_for_perfect_predictions():
    y = np.array([1.0, 2.0, 3.0])
    assert rmse_log(y, y) == pytest.approx(0.0)


def test_rmse_log_hand_computed():
    y_true_log = np.array([0.0, 0.0])
    y_pred_log = np.array([3.0, 4.0])
    # diffs = [-3, -4], squared = [9, 16], mean = 12.5
    assert rmse_log(y_true_log, y_pred_log) == pytest.approx(math.sqrt(12.5))


def test_mdape_backtransformed_hand_computed():
    y_true_log = np.array([0.0, 0.0, 0.0])
    y_pred_log = np.array([0.0, math.log(1.5), math.log(2.0)])
    # back-transformed: y_true = [1, 1, 1], y_pred = [1, 1.5, 2.0]
    # abs pct errors = [0, 0.5, 1.0] -> median = 0.5
    assert mdape_backtransformed(y_true_log, y_pred_log) == pytest.approx(0.5)
