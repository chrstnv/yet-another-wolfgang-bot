# Короткие команды вместо длинных. Питон берётся из .venv, так что
# активировать окружение не нужно: make test работает из чистой оболочки.

PYTHON := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

.DEFAULT_GOAL := help
.PHONY: help run test check record hooks image dev

help:  ## показать этот список
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | expand -t 12

run:  ## запустить бота
	$(PYTHON) main.py

dev:  ## запустить тестового бота на тестовой библиотеке (.env.dev)
	ENV_FILE=.env.dev $(PYTHON) main.py

test:  ## прогнать тесты
	$(PYTHON) -m pytest -q

check:  ## проверить библиотеку карточек
	$(PYTHON) -m tools.check_content

record:  ## принять текущие изъяны за норму
	$(PYTHON) -m tools.check_content --record

hooks:  ## поставить хуки перед коммитом
	sh hooks/install.sh

image:  ## собрать образ с карточками, как это делает CI
	@rm -rf content && mkdir -p content
	@cp -R $$(grep '^CONTENT_PATH=' .env | cut -d= -f2)/cards content/cards
	docker build -t wolfgang-bot:local .
