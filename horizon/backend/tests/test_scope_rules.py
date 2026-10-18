from app.domain.scope_rules import detect_scope, entity_status_from_scope

GD_SUBSIDY = "……本办法适用于在广东省内注册的中资商业银行、城市商业银行及农村金融机构……"


def test_domestic_only_detected():
    result = detect_scope(GD_SUBSIDY)
    assert result.suggestion == "domestic_only"
    assert any(h.category == "domestic_only" for h in result.hits)


def test_foreign_included_detected():
    text = "试点机构包括中资银行及在内地注册的外资银行。"
    assert detect_scope(text).suggestion == "foreign_included"


def test_no_hit_is_unclear():
    assert detect_scope("今日天气晴朗。").suggestion == "unclear"


def test_entity_status_mapping():
    # hsbc_cn 是境内外商独资法人银行：domestic_only → excluded（用例 1 的核心判定）
    assert entity_status_from_scope("hsbc_cn", "domestic_only") == "excluded"
    assert entity_status_from_scope("hsbc_cn", "foreign_included") == "covered"
    # hsbc_hk 是境外机构：境内主体限定 → na
    assert entity_status_from_scope("hsbc_hk", "domestic_only") == "na"


def test_group_affiliate_mention_only_flags():
    result = detect_scope(GD_SUBSIDY + "恒生银行表示关注。")
    assert result.group_affiliate_mention["mentioned"] is True
    # 不影响对汇丰实体的判定
    assert entity_status_from_scope("hsbc_cn", result.suggestion) == "excluded"
