# Пустой, но нужный: pytest кладёт папку с conftest.py в sys.path, и благодаря
# этому тесты импортируют content, quiz, progress напрямую — без установки пакета.
