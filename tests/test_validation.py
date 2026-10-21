"""质量问题清单必须可导出，但警告文案不能随坏点数无限增长。"""
import numpy as np
import pandas as pd
import pytest

from core.models import COLUMNS
from core.validation import summarize_values, validate_data


def frame(rows=50):
    frequency = np.linspace(2, 18, rows)
    data = pd.DataFrame({"frequency_ghz": frequency,
                         "eps_real": np.full(rows, 4.), "eps_imag": np.full(rows, .2),
                         "mu_real": np.full(rows, 1.5), "mu_imag": np.full(rows, .3)}, columns=COLUMNS)
    return data


def test_summarize_values_limits_and_counts():
    text = summarize_values(range(100))
    assert "共 100 点" in text
    assert len(text.split(",")) == 20  # 20 个值，截断说明附在末值之后


def test_negative_warning_is_truncated_but_details_are_complete():
    data = frame()
    data["eps_imag"] = -.2
    warnings, details = validate_data(data, "S")
    assert len(warnings[0]) < 400
    assert "共 50 点" in warnings[0]
    assert details["negative_fields"]["eps_imag"]["count"] == 50
    assert len(details["negative_fields"]["eps_imag"]["frequency_ghz"]) == 50


def test_nonfinite_error_message_capped_and_details_complete():
    data = frame(30)
    data.loc[5:, "mu_imag"] = np.nan
    with pytest.raises(ValueError) as info:
        validate_data(data, "S")
    error = info.value
    assert error.details["non_finite"] and len(error.details["non_finite"]) == 25
    assert "25 个" in str(error)
    assert len(str(error).splitlines()) == 21
