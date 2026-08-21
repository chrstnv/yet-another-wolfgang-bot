# Бот на сервере

Бот работает на виртуальной машине в Yandex Cloud, в контейнере. Новая версия
доезжает туда сама: коммит в `main` — и через пару минут на машине работает
новый образ. Правка карточек в соседнем репозитории делает то же самое.

Здесь описано, как это устроено и что придётся сделать руками один раз.

## Как это работает

```
   коммит в main ──▶ GitHub Actions ──▶ образ в Container Registry
                          │                        │
                          │  ssh с ключом,         │  docker compose pull
                          │  которому разрешена    ▼
                          └──────────────▶ машина: контейнер с ботом
```

В образ кладутся и код, и карточки — поэтому серверу не нужен ни git, ни доступ
к приватному репозиторию с контентом. Тег образа — хеш коммита: по нему всегда
видно, что именно сейчас работает, и откат сводится к запуску прежнего тега.

Пароли на машине не хранятся. Права в реестр она получает от своего сервисного
аккаунта через службу метаданных облака, а GitHub — через федерацию удостоверений,
без долгоживущего ключа в секретах.

Наружу бот не слушает ничего. Он работает на длинных опросах: соединение всегда
исходящее, Телеграм к нам не приходит никогда. Ни белый IP для входящих, ни
сертификат, ни открытый порт не нужны.

## Шаг 0. Проверить связь с Телеграмом

**Это делается первым.** Бот держится на длинных опросах, и без устойчивого
соединения с `api.telegram.org` остальное строить бессмысленно.

```bash
curl -sS -o /dev/null -w 'код %{http_code}, время %{time_total}\n' \
  https://api.telegram.org/bot$BOT_TOKEN/getMe

# длинные опросы — так ходит сам бот
for i in $(seq 1 30); do
  curl -s -m 70 "https://api.telegram.org/bot$BOT_TOKEN/getUpdates?timeout=50" \
    > /dev/null || echo "обрыв на попытке $i"
  sleep 1
done
```

Отвечает без обрывов — дальше по шагам. Если нет, у бота есть настройка
`TELEGRAM_PROXY`: он умеет ходить через прокси, см. раздел «Прокси».

## Шаг 1. Машина

```bash
# Docker из официального репозитория: штатный docker.io в Ubuntu 22.04 слишком стар
curl -fsSL https://get.docker.com | sudo sh

# Оболочка нужна настоящая: выкладка приходит по SSH, а с nologin вход не
# состоится вовсе. От самовольных действий защищает не оболочка, а command=
# в authorized_keys — см. шаг 3
sudo useradd --system --create-home --shell /bin/sh --groups docker wolfgang
sudo mkdir -p /opt/wolfgang/data
sudo chown -R wolfgang:wolfgang /opt/wolfgang

# Внутри контейнера бот работает под uid 1000, и это не тот же пользователь,
# что wolfgang на хосте: у системной учётной записи uid другой. Смонтированный
# каталог принадлежит владельцу по номеру, а не по имени, — иначе бот не сможет
# писать базу
sudo chown -R 1000:1000 /opt/wolfgang/data
```

Положить на машину `compose.yaml`, `deploy/deploy.sh` (как `/opt/wolfgang/deploy.sh`),
`deploy/watchdog.sh` и `deploy/backup.sh`, все три — `chmod 755`, владелец `root`,
чтобы пользователь `wolfgang` не мог их переписать.

`/opt/wolfgang/image.env` — обычный файл, владелец `wolfgang` (выкладка правит в
нём тег бота):

```
BOT_IMAGE=cr.yandex/<идентификатор реестра>/wolfgang-bot:latest
PROXY_IMAGE=cr.yandex/<идентификатор реестра>/wolfgang-proxy:latest
COMPOSE_PROFILES=proxy
```

Последняя строка включает прокси. Там, где Телеграм доступен напрямую, её
просто не пишут — и служба прокси не поднимается вовсе.

`/opt/wolfgang/.env` — правами `600`, владелец `wolfgang`:

```
BOT_TOKEN=...
ADMIN_CHAT_ID=...
DB_PATH=/data/bot.db
STATE_PATH=/data/state.pickle
CONTENT_PATH=/app/content
HEARTBEAT_PATH=/data/heartbeat
TELEGRAM_PROXY=socks5://proxy:1080
```

`proxy` здесь — имя службы в compose, а не адрес в сети: бот и прокси стоят
рядом, и наружу машины этот порт не выставляется.

Перенести накопленное **до первого запуска**, иначе бот заведёт пустую базу:

```bash
scp bot.db state.pickle сервер:/tmp/
sudo mv /tmp/bot.db /tmp/state.pickle /opt/wolfgang/data/
sudo chown 1000:1000 /opt/wolfgang/data/*
```

**Завести второго бота у @BotFather для разработки.** Два процесса с одним
токеном Телеграм не терпит: он отдаёт обновления кому-то одному, и локальный
`make run` начнёт отбирать их у сервера (`Conflict: terminated by other getUpdates`).

## Шаг 2. Облако

1. Container Registry: создать реестр, запомнить его идентификатор.
2. Сервисный аккаунт `wolfgang-vm` с ролью `container-registry.images.puller`,
   привязать к виртуальной машине — по нему `deploy.sh` берёт токен из метаданных.
3. Сервисный аккаунт `wolfgang-ci` с ролью `container-registry.images.pusher`
   и авторизованный ключ к нему — он поедет в секреты GitHub. На вырост:
   тот же вход умеет работать по федерации удостоверений, без долгоживущего
   ключа, но настраивается это заметно дольше.
4. Группа безопасности: входящий — только 22, исходящий — весь. Больше боту
   ничего не нужно.
5. Бакет в Object Storage для бэкапов, правило жизненного цикла — 30 дней.
   Сервисному аккаунту машины дать `storage.uploader`.
6. Расписание снимков загрузочного диска: раз в неделю, хранить 4.

## Шаг 3. Ключ выкладки

На машине, от имени `wolfgang`:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
# сюда — публичная часть ключа, который лежит в секретах GitHub
echo 'command="/opt/wolfgang/deploy.sh",restrict ssh-ed25519 AAAA... github-deploy' \
  >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

`command=` и `restrict` — главное здесь. Этим ключом нельзя получить оболочку,
только запустить выкладку; утечка секрета из GitHub перестаёт быть катастрофой.
Хеш коммита приезжает в `SSH_ORIGINAL_COMMAND` и проверяется скриптом на то, что
это действительно хеш, а не команда.

## Шаг 4. Секреты в GitHub

В репозитории бота:

| Секрет | Что это |
|---|---|
| `YC_SA_JSON` | ключ сервисного аккаунта `wolfgang-ci` целиком, как выдал `yc` |
| `YC_REGISTRY_ID` | идентификатор реестра |
| `CONTENT_DEPLOY_KEY` | приватная часть read-only deploy key к репозиторию с карточками |
| `DEPLOY_HOST` | адрес машины |
| `DEPLOY_USER` | `wolfgang` |
| `DEPLOY_KEY` | приватная часть ключа выкладки |
| `DEPLOY_KNOWN_HOSTS` | вывод `ssh-keyscan <адрес машины>` |

`DEPLOY_KNOWN_HOSTS` не для красоты: без него выкладка соглашается на любой ключ
сервера, а это ровно та дверь, в которую входит человек посередине.

В репозитории с карточками — `BOT_DISPATCH_TOKEN`: мелкозернистый токен с правом
`actions: write` на репозиторий бота, чтобы правка карточек будила пересборку.

Пока секретов нет, оба workflow не краснеют, а пропускают свои шаги с пометкой.

## Шаг 5. Сторож и бэкапы

Два таймера systemd. Сторож — потому что политика перезапуска Docker смотрит
только на код возврата и на провалившийся healthcheck не реагирует вовсе.

```ini
# /etc/systemd/system/wolfgang-watchdog.service
[Service]
Type=oneshot
ExecStart=/opt/wolfgang/watchdog.sh

# /etc/systemd/system/wolfgang-watchdog.timer
[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/wolfgang-backup.service
[Service]
Type=oneshot
Environment=BACKUP_BUCKET=имя-бакета
ExecStart=/opt/wolfgang/backup.sh

# /etc/systemd/system/wolfgang-backup.timer
[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/wolfgang-proxy-check.service
[Service]
Type=oneshot
ExecStart=/opt/wolfgang/proxy-check.sh

# /etc/systemd/system/wolfgang-proxy-check.timer
[Timer]
OnBootSec=10min
OnUnitActiveSec=15min
[Install]
WantedBy=timers.target
```

```bash
sudo systemctl enable --now wolfgang-watchdog.timer wolfgang-backup.timer \
                           wolfgang-proxy-check.timer wolfgang-proxy-refresh.timer
```

Сторож смотрит на контейнеры, проверка прокси — на канал до Телеграма. Это
разные отказы: при мёртвом прокси бот жив, здоров и совершенно бесполезен.

## Восстановление

Бэкап, который не восстанавливали, бэкапом не является. Проделать один раз
сразу после настройки:

```bash
yc storage s3 ls s3://<бакет>/db/
yc storage s3 cp s3://<бакет>/db/<нужный>.tar.gz /tmp/
mkdir /tmp/проверка && tar -xzf /tmp/<нужный>.tar.gz -C /tmp/проверка

# убедиться, что ответы на месте
sqlite3 /tmp/проверка/bot.db 'SELECT count(*) FROM answers;'

# вернуть в работу
docker compose stop
sudo cp /tmp/проверка/bot.db /opt/wolfgang/data/bot.db
sudo chown 1000:1000 /opt/wolfgang/data/bot.db
docker compose start
```

## Откат версии

```bash
sudo -u wolfgang /opt/wolfgang/deploy.sh   # с SSH_ORIGINAL_COMMAND=<прежний хеш>
```

Либо руками: поправить тег в `/opt/wolfgang/image.env` и запустить
`docker compose up -d`.

## Прокси

Там, где прямого доступа к `api.telegram.org` нет, бот умеет ходить через
прокси SOCKS5. Рядом с ним поднимается служба `proxy` — клиент Xray, — а бот
получает адрес настройкой:

```
TELEGRAM_PROXY=socks5://proxy:1080
```

В обход уходит **только трафик бота**: реестр образов, входящий SSH для
выкладки и всё остальное продолжают ходить напрямую. Это и есть причина взять
прокси, а не менять маршруты машины целиком — иначе вместе с ними сломалась бы
выкладка.

Служба включается профилем, поэтому там, где она не нужна, её просто нет:

```
COMPOSE_PROFILES=proxy
```

Конфиг `proxy.json` собирается инструментом `tools/proxy_config.py` из ссылки
на узел или из ссылки-подписки; он понимает `vless://`, `trojan://` и `ss://`.
Ссылка — секрет: держите её и готовый конфиг с правами 600, в репозиторий они
не попадают.

Владельцем конфига должен быть **65534** — это `nobody`, под которым работает
Xray внутри контейнера. Смонтированный файл сохраняет права хозяйской системы,
и root-овый файл с правами 600 контейнер прочитать не сможет:

```bash
sudo chown 65534:65534 /opt/wolfgang/proxy.json
sudo chmod 600 /opt/wolfgang/proxy.json
``` `proxy-refresh.sh` перечитывает подписку по расписанию и
перезапускает службу, если узел сменился; `proxy-check.sh` проверяет, что канал
жив, и поднимает прокси, если тот отвалился.

Подробности настройки этой машины — в приватном репозитории с контентом,
`docs/сервер.md`.

## Что смотреть, когда что-то не так

```bash
docker compose ps                    # состояние и здоровье
docker compose logs -f --tail 100    # логи бота
ls -l /opt/wolfgang/data/heartbeat   # когда бот последний раз отмечался
systemctl list-timers 'wolfgang-*'   # сторож и бэкапы
```

О поломках бот жалуется сам — присылает короткое сообщение в чат владельца, не
чаще раза в пять минут. Подробности со стеком остаются в логах.
