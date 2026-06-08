"""Regression test: a NULL value in a row must not use the wrong column for the chart label.

The None-handling branch of get_chart_values_by_data labeled rows with data[string_index].
string_index is -1 when the result has no string column (a datetime/id primary dimension),
so the row was labeled with the LAST column's value instead of the dimension. With name: str
on ValueItem, that raises a ValidationError on a numeric last column (current pydantic), and
mislabels the series under lenient configs. The non-NULL branch correctly uses primary_index.

  with the fix -> PASS (NULL rows labeled by the dimension, like the non-NULL rows)
  without it   -> FAIL (raises / mislabels: the last column's value is used)
"""
import datetime
from dbgpt_app.scene.chat_dashboard.data_loader import DashboardDataLoader


def test_null_row_uses_primary_index_not_string_index():
    loader = DashboardDataLoader()
    field_names = ["event_date", "sales", "cost"]
    datas = [
        (datetime.date(2024, 1, 1), None, 150),   # NULL -> None-handling branch
        (datetime.date(2024, 1, 2), 200, 100),    # normal row
    ]
    _, values = loader.get_chart_values_by_data(field_names, datas, "SELECT ...")
    names = [str(v.name) for v in values]
    assert "150" not in names, f"NULL row used the last-column value as label: {names}"
    assert any("2024-01-01" in n for n in names), f"Expected date label, got: {names}"
