from services.furniture_query_terms import is_delete_marker


def test_is_delete_marker_matches_prompt_contract():
    assert is_delete_marker("__DELETE__") is True
    assert is_delete_marker("  __DELETE__  ") is True
    assert is_delete_marker("__delete__") is True
    assert is_delete_marker("Стул") is False
    assert is_delete_marker("") is False
