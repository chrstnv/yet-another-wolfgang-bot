from telegram import ReplyKeyboardMarkup

RANDOM_QUIZ_LABEL = "🎲 Случайный квиз"
STREAK_LABEL = "🔥 Серия"
REVIEW_LABEL = "🔁 Работа над ошибками"
PROGRESS_LABEL = "📈 Прогресс"
FAVOURITES_LABEL = "❤️ Избранное"
SETTINGS_LABEL = "⚙️ Настройки"

MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [RANDOM_QUIZ_LABEL, STREAK_LABEL],
        [REVIEW_LABEL, PROGRESS_LABEL],
        [FAVOURITES_LABEL, SETTINGS_LABEL],
    ],
    resize_keyboard=True,
)
