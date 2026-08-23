from telegram import ReplyKeyboardMarkup

RANDOM_QUIZ_LABEL = "🎲 Случайный квиз"
STREAK_LABEL = "🔥 Серия"
REVIEW_LABEL = "🔁 Работа над ошибками"
PROGRESS_LABEL = "📈 Прогресс"
FAVOURITES_LABEL = "❤️ Избранное"
SETTINGS_LABEL = "⚙️ Настройки"

# Клавиатура меню живёт не в боте, а в клиенте: он показывает ту, что пришла
# последней, и сам её не обновляет. Поэтому новый пункт достаётся только тем,
# кто заново нажал «Старт», — если не следить за этим отдельно.
#
# Номер повышается при **любой** правке меню: по нему бот понимает, что человек
# видит устаревшую клавиатуру, и присылает свежую при первом же его действии
MENU_VERSION = 2

MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [RANDOM_QUIZ_LABEL, STREAK_LABEL],
        [REVIEW_LABEL, PROGRESS_LABEL],
        [FAVOURITES_LABEL, SETTINGS_LABEL],
    ],
    resize_keyboard=True,
)
