from keyboards import ALL_QUIZZES_LABEL, COLLECTION_LABEL, SETTINGS_LABEL

SECTION_REPLIES = {
    ALL_QUIZZES_LABEL: "🎯 Все квизы скоро появятся!",
    COLLECTION_LABEL: "❤️ Коллекция скоро появится!",
    SETTINGS_LABEL: "⚙️ Настройки скоро появятся!",
}

GREETING = (
    "Привет! Здесь учатся узнавать классику на слух.\n\n"
    "Звучит фрагмент — вы выбираете из четырёх вариантов.\n\n"
    "Начните со «🎲 Случайный квиз»."
)

QUESTION = "🎵 Послушайте фрагмент. Какое это произведение?"

VERDICTS = {
    "perfect": "Идеально. {correct} из {total}, ни одной ошибки.",
    "good": "{correct} из {total}. Ухо уже кое-что помнит.",
    "weak": "{correct} из {total}. Классику не угадывают — её узнают, а это дело наживное.",
}
