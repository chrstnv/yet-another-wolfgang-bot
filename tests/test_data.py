import pytest

import data

def test_ids_are_unique():
    assert len(set(card["id"] for card in data.CARDS)) == len(data.CARDS)

def test_ids_are_strings():
    for card in data.CARDS:
        assert isinstance(card["id"], str)

def test_every_card_has_a_title():
    for card in data.CARDS:
        assert card.get("title"), card["id"]

def test_distractors_point_to_existing_cards():
    for card in data.CARDS:
        for distractor_id in card.get("distractors", []):
            assert distractor_id in data.CARDS_BY_ID, f"{card['id']} -> {distractor_id}"

def test_card_is_never_its_own_distractor():
    for card in data.CARDS:
        assert card["id"] not in card.get("distractors", []), card["id"]

def test_library_is_big_enough_for_four_options():
    assert len(data.CARDS) >= 4

def test_there_is_something_to_play():
    assert data.PLAYABLE_CARDS

@pytest.mark.parametrize("card", data.PLAYABLE_CARDS, ids=lambda card: card["id"])
def test_playable_card_has_facts(card):
    assert card.get("facts")

@pytest.mark.parametrize("card", data.PLAYABLE_CARDS, ids=lambda card: card["id"])
def test_playable_card_has_fragment(card):
    assert card.get("fragment")

@pytest.mark.parametrize("card", data.PLAYABLE_CARDS, ids=lambda card: card["id"])
def test_playable_card_has_a_real_looking_audio_file_id(card):
    file_id = card["audio_file_id"]

    assert len(file_id) > 40
    assert " " not in file_id

@pytest.mark.parametrize("card", data.PLAYABLE_CARDS, ids=lambda card: card["id"])
def test_playable_card_credits_the_recording(card):
    assert card["recording"]["performer"]
    assert card["recording"]["source"]
