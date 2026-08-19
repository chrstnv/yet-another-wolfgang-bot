from core.texts import (
    ANSWER_CORRECT, ANSWER_WRONG, CORRECT_SIGN, QUESTION_SIGN, QUESTION_VARIANTS,
    STREAK_TITLE_ZERO, STREAK_OVER_SIGN, WRONG_SIGN, wolfgang,
)

def test_wolfgang_wraps_the_fallback_in_a_custom_emoji():
    assert wolfgang("✅", "42") == '<tg-emoji emoji-id="42">✅</tg-emoji>'

def test_wolfgang_leaves_the_plain_emoji_until_the_picture_is_drawn():
    assert wolfgang("🎵") == "🎵"

def test_every_sign_falls_back_to_something_readable():
    # без Premium у владельца и на старых клиентах видно только запасное
    for sign, fallback in [
        (CORRECT_SIGN, "✅"), (WRONG_SIGN, "❌"),
        (STREAK_OVER_SIGN, "🙄"), (QUESTION_SIGN, "🎵"),
    ]:
        assert fallback in sign

def test_the_answer_signs_stand_before_the_reply():
    assert ANSWER_CORRECT == f"{CORRECT_SIGN} <i>{{reply}}</i>"
    assert ANSWER_WRONG == f"{WRONG_SIGN} <i>{{reply}}</i>"

def test_every_question_carries_wolfgang():
    assert all(line.startswith(QUESTION_SIGN) for line in QUESTION_VARIANTS)

def test_a_streak_of_nothing_gets_the_eye_roll():
    assert STREAK_TITLE_ZERO.startswith(STREAK_OVER_SIGN)
