from parser import deterministic_parse


def test_parses_supported_time_formats():
    text = """today 20:00 deep work\ntomorrow 20.00 reading\nmon 20 gym\n20.00 to 23.00 project block\n8pm walk\n8 pm journal"""
    items = deterministic_parse(text)
    assert len(items) == 6
    assert items[0].due_time == "20:00"
    assert items[1].due_time == "20:00"
    assert items[2].due_time == "20:00"
    assert items[3].window_start is not None
    assert items[3].window_end is not None
    assert items[4].due_time == "20:00"
    assert items[5].due_time == "20:00"


def test_ambiguous_date_returns_error():
    items = deterministic_parse("11/12/2026 20:00 study")
    assert len(items) == 1
    assert items[0].parse_error


def test_one_line_to_one_task():
    items = deterministic_parse("20:00-23:00 write report")
    assert len(items) == 1
    assert items[0].title.startswith("write report")
