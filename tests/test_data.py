import data

def test_ids_are_unique():
    assert len(set(card["id"] for card in data.CARDS)) == len(data.CARDS)

def test_ids_are_strings():
    assert all(isinstance(card["id"], str) for card in data.CARDS)
    for card in data.CARDS:
        assert isinstance(card["id"], str)

def test_options_have_exactly_four_variants():
    for card in data.CARDS:
        assert len(card["options"]) == 4

def test_correct_index_is_within_range():
    for card in data.CARDS:
        assert 0 <= card["correct_index"] < len(card["options"])

def test_facts_are_not_empty():
    for card in data.CARDS:
        assert card["facts"]

def test_audio_file_id_looks_real():
    for card in data.CARDS:
        file_id = card["audio_file_id"]
        assert len(file_id) > 40 and " " not in file_id

def test_recording_has_performer_and_source():
    for card in data.CARDS:
        assert card["recording"]["performer"]
        assert card["recording"]["source"]