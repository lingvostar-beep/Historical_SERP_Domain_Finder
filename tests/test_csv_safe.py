from app.services.csv_safe import csv_guard, write_csv_rows


def test_formula_guard():
    assert csv_guard("=1+1").startswith("'")
    assert csv_guard("normal") == "normal"


def test_bom_present():
    data = write_csv_rows(["a"], [["x"]])
    assert data.startswith(b"\xef\xbb\xbf")
