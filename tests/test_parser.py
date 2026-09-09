import numpy as np
import pytest
from core.parser import read_sample


def test_csv_and_signed_conversion(tmp_path, frame):
    path = tmp_path / "test.csv"
    frame[["eps_imag", "mu_imag"]] *= -1
    frame.to_csv(path, index=False)
    sample = read_sample(path, imaginary_convention="signed")
    assert sample.data.eps_imag.iloc[0] == .2
    assert sample.metadata["imaginary_conversion"] == "negate once"
    assert not sample.metadata["convention_confirmed"]


def test_excel_mapping_hz(tmp_path, frame):
    path = tmp_path / "test.xlsx"
    frame.frequency_ghz *= 1e9
    mapping = {col: f"source_{col}" for col in frame.columns}
    frame.rename(columns=mapping).to_excel(path, index=False, sheet_name="test")
    sample = read_sample(path, sheet="test", column_map=mapping, frequency_unit="Hz", imaginary_convention="loss")
    np.testing.assert_allclose(sample.data.frequency_ghz, [2, 3, 4])


def test_memp_observed_structure(tmp_path):
    path = tmp_path / "test.memp"
    text = "样品名称：synthetic\n测试频率：2~3GHz,2\n频率(GHz)\t介电实部\t介电虚部\t磁导实部\t磁导虚部\n2\t4\t-.2\t1\t.3\n3\t4\t.2\t1\t.3\n"
    raw = text.encode("gbk")
    path.write_bytes(raw)
    sample = read_sample(path, imaginary_convention="loss")
    assert sample.data.eps_imag.iloc[0] == -.2
    assert sample.name == "synthetic"
    assert path.read_bytes() == raw
    path.write_bytes(text.replace("2~3GHz,2", "2~3GHz,3").encode("gbk"))
    with pytest.raises(ValueError, match="不完整"):
        read_sample(path, imaginary_convention="loss")


@pytest.mark.parametrize("failure", ["nan", "infinity", "duplicate", "reverse", "missing_column"])
def test_bad_csv_refused(tmp_path, frame, failure):
    if failure == "nan": frame.loc[1, "mu_imag"] = np.nan
    if failure == "infinity": frame.loc[1, "mu_imag"] = np.inf
    if failure == "duplicate": frame.loc[1, "frequency_ghz"] = 2
    if failure == "reverse": frame = frame.iloc[::-1]
    if failure == "missing_column": frame = frame.drop(columns="mu_imag")
    path = tmp_path / "bad.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        read_sample(path, imaginary_convention="loss")


def test_unknown_sdat_refused(tmp_path):
    path = tmp_path / "unknown.sdat"
    path.write_text("2 1 2 3 4 5 6 7 8")
    with pytest.raises(ValueError, match="禁止猜测"):
        read_sample(path, imaginary_convention="loss")


@pytest.mark.parametrize("body", ["2,4,.2,1,.3,999", "2,4,.2,1", ""])
def test_csv_ragged_or_blank_row_rejected(tmp_path, body):
    path = tmp_path / "ragged.csv"
    path.write_text("frequency_ghz,eps_real,eps_imag,mu_real,mu_imag\n"+body+"\n3,4,.2,1,.3\n")
    with pytest.raises(ValueError):
        read_sample(path, imaginary_convention="loss")


def test_duplicate_csv_header_rejected(tmp_path):
    path = tmp_path / "duplicate.csv"
    path.write_text("frequency_ghz,eps_real,eps_imag,mu_real,mu_imag,eps_real\n2,4,.2,1,.3,5\n3,4,.2,1,.3,5\n")
    with pytest.raises(ValueError, match="重复"):
        read_sample(path, imaginary_convention="loss")


def test_convention_required(tmp_path, frame):
    path = tmp_path / "input.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="显式"):
        read_sample(path)


def test_missing_unit_with_nonstandard_column_refused(tmp_path, frame):
    mapping = {col: col for col in frame.columns}
    mapping["frequency_ghz"] = "Frequency"
    path = tmp_path / "input.csv"
    frame.rename(columns=mapping).to_csv(path, index=False)
    with pytest.raises(ValueError, match="单位"):
        read_sample(path, column_map=mapping, imaginary_convention="loss")
