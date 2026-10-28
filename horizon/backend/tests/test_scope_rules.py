from app.domain.scope_rules import detect_scope, entity_relevance_from_scope

GD_SUBSIDY = "……本办法适用于在广东省内注册的中资商业银行、城市商业银行及农村金融机构……"


def test_domestic_only_detected():
    result = detect_scope(GD_SUBSIDY)
    assert result.relevance == "low"
    assert any(hit.category == "low" for hit in result.hits)


def test_foreign_included_detected():
    text = "试点机构包括中资银行及在内地注册的外资银行。"
    assert detect_scope(text).relevance == "high"


def test_no_hit_is_unclear():
    assert detect_scope("今日天气晴朗。").relevance == "unclear"


def test_entity_relevance_mapping():
    assert entity_relevance_from_scope("hsbc_cn", "low") == "low"
    assert entity_relevance_from_scope("hsbc_cn", "high") == "high"
    assert entity_relevance_from_scope("hsbc_hk", "low") == "na"


def test_group_affiliate_mention_only_flags():
    result = detect_scope(GD_SUBSIDY + "恒生银行表示关注。")
    assert result.group_affiliate_mention["mentioned"] is True
    assert entity_relevance_from_scope("hsbc_cn", result.relevance) == "low"
