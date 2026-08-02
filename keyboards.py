from telegram import ReplyKeyboardMarkup

RANDOM_QUIZ_LABEL = "🎲 Случайный квиз"
ALL_QUIZZES_LABEL = "🎯 Все квизы"
COLLECTION_LABEL = "❤️ Коллекция"
PROGRESS_LABEL = "📈 Прогресс"
SETTINGS_LABEL = "⚙️ Настройки"

MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [RANDOM_QUIZ_LABEL, ALL_QUIZZES_LABEL],
        [COLLECTION_LABEL, PROGRESS_LABEL],
        [SETTINGS_LABEL],
    ],
    resize_keyboard=True,
)
