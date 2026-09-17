from utils.furniture_label_rules import load_furniture_label_rules


def test_load_furniture_label_rules_and_resolve_type(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(
        """
        {
          "version": "v1",
          "vision_label_to_type": {
            "Couch": "sofa"
          },
          "types": {
            "sofa": {
              "search_enabled": true,
              "query_terms": ["диван"],
              "include_tokens": ["диван"],
              "exclude_tokens": ["чехол"]
            }
          }
        }
        """,
        encoding="utf-8",
    )
    rules = load_furniture_label_rules(rules_file)
    assert rules.version == "v1"
    rule = rules.resolve_type_rule("Couch")
    assert rule.type_name == "sofa"
    assert rule.search_enabled is True
    assert "диван" in rule.query_terms


def test_load_furniture_label_rules_fallback_for_unknown_label(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(
        """
        {
          "version": "v1",
          "vision_label_to_type": {},
          "types": {}
        }
        """,
        encoding="utf-8",
    )
    rules = load_furniture_label_rules(rules_file)
    rule = rules.resolve_type_rule("Dining Table")
    assert rule.search_enabled is True
    assert rule.type_name == "dining_table"
    assert "dining" in rule.query_terms
