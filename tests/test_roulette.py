from tools.add_card import MAX_GAIN, TARGET_PEAK
from tools.roulette import (
    APART, HEAD, LENGTH, TAIL, evens_out, fits, gain_for, taken_places,
)

HOUR = 600.0

def test_the_beginning_of_a_recording_is_left_alone():
    """Там вступления, настройка оркестра и тишина перед первой нотой."""
    assert not fits(HOUR * HEAD - 1, HOUR, [])
    assert fits(HOUR * HEAD + 1, HOUR, [])

def test_the_end_of_a_recording_is_left_alone():
    """Там затихания и аплодисменты."""
    assert not fits(HOUR * (1 - TAIL) - LENGTH + 1, HOUR, [])
    assert fits(HOUR * (1 - TAIL) - LENGTH - 1, HOUR, [])

def test_a_window_does_not_land_on_what_is_already_taken():
    """Отобранный руками фрагмент узнают — в этом режиме он ни к чему."""
    assert not fits(300.0, HOUR, [(300.0, 35.0)])

def test_a_window_keeps_its_distance_from_the_taken():
    """Иначе два «случайных» места окажутся почти одним и тем же."""
    assert not fits(300.0 + LENGTH + APART - 5, HOUR, [(300.0, 35.0)])
    assert fits(300.0 + 35.0 + APART + 1, HOUR, [(300.0, 35.0)])

def test_a_window_before_the_taken_one_also_keeps_away():
    assert not fits(300.0 - LENGTH - 5, HOUR, [(300.0, 35.0)])
    assert fits(300.0 - LENGTH - APART - 1, HOUR, [(300.0, 35.0)])

def test_a_short_recording_leaves_no_room():
    """Полминуты: после отрезанных краёв на кусок в 25 секунд места нет."""
    assert not any(fits(float(start), 30.0, []) for start in range(30))

def test_a_minute_is_already_enough():
    assert any(fits(float(start), 60.0, []) for start in range(60))

def test_the_marked_fragment_counts_as_taken():
    card = {"fragments": [{"start": "12.5", "duration": "35"}]}

    assert taken_places(card) == [(12.5, 35.0)]

def test_a_fragment_without_a_mark_is_not_counted():
    """Засечка записана не у всех: чего не знаем, того и не бережём."""
    card = {"fragments": [{"name": "Утро"}]}

    assert taken_places(card) == []

def test_pieces_cut_earlier_are_counted_too():
    card = {"roulette": [{"start": "184.0", "duration": "25"}]}

    assert taken_places(card) == [(184.0, 25.0)]

def test_a_quiet_piece_is_lifted_to_the_others():
    """Куски не должны прыгать по громкости от вопроса к вопросу."""
    assert gain_for(-28.0, -9.0) == 5.0

def test_a_loud_piece_is_brought_down():
    assert gain_for(-12.0, -1.0) == -6.0

def test_the_lift_never_clips_the_peaks():
    """Запас до максимума важнее попадания в цель."""
    assert gain_for(-30.0, -2.0) == TARGET_PEAK + 2.0

def test_the_lift_has_a_ceiling():
    """Выше усилитель тянет вместе с оркестром зал, ленту и всё остальное."""
    assert gain_for(-40.0, -25.0) == MAX_GAIN

def test_a_piece_that_cannot_be_evened_out_is_refused():
    """Средний уровень низкий, а пик у потолка — это щелчок, а не музыка."""
    assert not evens_out(-26.0, -1.0)

def test_quiet_music_is_still_music():
    """Adagio sostenuto держится на тридцати пяти децибелах и имеет право."""
    assert evens_out(-33.1, -16.2)

def test_a_piece_that_can_be_lifted_is_kept():
    assert evens_out(-28.0, -9.0)

def test_the_gap_can_be_given_up():
    """На короткой записи зазор съедает всё свободное место."""
    busy = [(0.0, 35.0)]

    assert not fits(38.0, 73.0, busy)
    assert fits(38.0, 73.0, busy, gap=0.0)

def test_pieces_never_overlap_even_without_a_gap():
    assert not fits(20.0, 73.0, [(0.0, 35.0)], gap=0.0)
