from tools import check_content

def test_ratchet_is_quiet_when_a_flaw_stays_put():
    assert check_content.grown({"лицензия не указана": 156}, {"лицензия не указана": 156}) == []

def test_ratchet_is_quiet_when_a_flaw_shrinks():
    assert check_content.grown({"лицензия не указана": 150}, {"лицензия не указана": 156}) == []

def test_ratchet_speaks_up_when_a_flaw_grows():
    grown = check_content.grown({"лицензия не указана": 157}, {"лицензия не указана": 156})

    assert grown == ["лицензия не указана: было 156, стало 157"]

def test_ratchet_ignores_a_flaw_the_baseline_has_never_seen():
    assert check_content.grown({"новая проверка": 3}, {}) == []
