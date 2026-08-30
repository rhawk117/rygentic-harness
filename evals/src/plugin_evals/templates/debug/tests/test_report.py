from src.report import summarize

def test_summary_count():
    assert summarize(["a", "b", "c"]) == "3 items"
