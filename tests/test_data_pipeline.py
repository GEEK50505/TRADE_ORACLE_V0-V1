"""Basic smoke tests for `data.data_pipeline`.

These tests are lightweight and use a synthetic DataFrame so they do not
require network access. They do require `pandas` to be installed.
"""

import pytest


def _has_pandas():
    try:
        import pandas  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_pandas(), reason="pandas not installed")
def test_compute_indicators_basic():
    import pandas as pd
    from data.data_pipeline import compute_indicators

    idx = pd.date_range(start="2021-01-01", periods=60, freq="H")
    df = pd.DataFrame({
        "open": range(60),
        "high": [x + 0.5 for x in range(60)],
        "low": [x - 0.5 for x in range(60)],
        "close": [float(x) for x in range(60)],
        "volume": [1.0] * 60,
    }, index=idx)

    res = compute_indicators(df)

    assert "sma50" in res.columns
    assert "ema20" in res.columns
    assert "rel_weak_14" in res.columns
    assert not res["sma50"].isnull().all()
