"""Everything the bot says, in English (default), Russian and Ukrainian.

Button and command names are Telegram's own strings (translations.telegram.org, the Android and
iOS apps): Add Channel, Choose a Channel, Channels, Pause, Resume, Remove, Settings, Help,
Notifications, Language, On, Off, Back, Stop, Cancel. Telegram's Russian writes «Вы/Ваш» with a
capital letter, its Ukrainian does not.
"""

from __future__ import annotations

LANGS = ("en", "ru", "uk")
LANG_NAMES = {"en": "English", "ru": "Русский", "uk": "Українська"}


def lang_of(code: str | None) -> str:
    """The bot's language for a Telegram app language code."""
    code = (code or "").lower().split("-")[0]
    return code if code in LANGS else "en"


T: dict[str, dict[str, str]] = {
    # profile ------------------------------------------------------------------------------------
    "name": {"en": "Feed", "ru": "Лента", "uk": "Стрічка"},
    "about": {
        "en": "This bot sends you new posts from the public channels you choose.",
        "ru": "Этот бот присылает новые публикации публичных каналов, которые Вы выберете.",
        "uk": "Цей бот надсилає нові публікації публічних каналів, які ви виберете.",
    },
    "description": {
        "en": (
            "Choose public channels, and their new posts will come here, each as a link with a preview. "
            "Tap a preview to open the post with comments. You don't need to join the channels.\n\n"
            "Add Channel: pick it from your chats, send its @username or t.me link, or forward any of its posts. Several at once are fine.\n"
            "Channels: pause or remove any of them.\n\n"
            "The bot is free and keeps only your list of channels and your settings."
        ),
        "ru": (
            "Выберите публичные каналы, и их новые публикации будут приходить сюда, каждая — ссылкой с предпросмотром. "
            "Нажмите на предпросмотр, чтобы открыть публикацию с комментариями. Подписываться на каналы не нужно.\n\n"
            "Добавить канал: выберите его среди Ваших чатов, пришлите его @username или ссылку t.me либо перешлите любую его публикацию. Можно сразу несколько.\n"
            "Каналы: поставьте любой на паузу или удалите.\n\n"
            "Бот бесплатный и хранит только список Ваших каналов и Ваши настройки."
        ),
        "uk": (
            "Виберіть публічні канали, і їхні нові публікації надходитимуть сюди, кожна — посиланням із передоглядом. "
            "Натисніть на передогляд, щоб відкрити публікацію з коментарями. Підписуватися на канали не потрібно.\n\n"
            "Додати канал: виберіть його серед ваших чатів, надішліть його @username чи посилання t.me або перешліть будь-яку його публікацію. Можна одразу кілька.\n"
            "Канали: поставте будь-який на паузу або видаліть.\n\n"
            "Бот безплатний і зберігає лише список ваших каналів і ваші налаштування."
        ),
    },
    "cmd_add": {"en": "Add Channel", "ru": "Добавить канал", "uk": "Додати канал"},
    "cmd_channels": {"en": "Channels", "ru": "Каналы", "uk": "Канали"},
    "cmd_settings": {"en": "Settings", "ru": "Настройки", "uk": "Налаштування"},
    "cmd_help": {"en": "Help", "ru": "Помощь", "uk": "Допомога"},
    # buttons ------------------------------------------------------------------------------------
    "btn_choose": {"en": "Choose a Channel", "ru": "Выбрать канал", "uk": "Виберіть канал"},
    "btn_pause": {"en": "Pause", "ru": "Пауза", "uk": "Пауза"},
    "btn_resume": {"en": "Resume", "ru": "Возобновить", "uk": "Продовжити"},
    "btn_remove": {"en": "Remove", "ru": "Удалить", "uk": "Видалити"},
    "btn_notifications": {"en": "Notifications: {v}", "ru": "Уведомления: {v}", "uk": "Сповіщення: {v}"},
    "btn_language": {"en": "Language: {v}", "ru": "Язык: {v}", "uk": "Мова: {v}"},
    "btn_back": {"en": "Back", "ru": "Назад", "uk": "Назад"},
    "btn_stop": {"en": "Stop", "ru": "Остановить", "uk": "Зупинити"},
    "btn_cancel": {"en": "Cancel", "ru": "Отмена", "uk": "Скасувати"},
    "btn_done": {"en": "Done", "ru": "Готово", "uk": "Готово"},
    "on": {"en": "On", "ru": "Включены", "uk": "Увімкнено"},
    "off": {"en": "Off", "ru": "Отключены", "uk": "Вимкнено"},
    # messages -----------------------------------------------------------------------------------
    "start": {
        "en": (
            "Choose public channels, and their new posts will come here, each as a link with a preview. "
            "Tap a preview to open the post with comments.\n\n"
            "Tap “Choose a Channel” below, send a channel's @username or t.me link, or forward any of its posts. Several at once are fine."
        ),
        "ru": (
            "Выберите публичные каналы, и их новые публикации будут приходить сюда, каждая — ссылкой с предпросмотром. "
            "Нажмите на предпросмотр, чтобы открыть публикацию с комментариями.\n\n"
            "Нажмите «Выбрать канал» внизу, пришлите @username канала или ссылку t.me либо перешлите любую его публикацию. Можно сразу несколько."
        ),
        "uk": (
            "Виберіть публічні канали, і їхні нові публікації надходитимуть сюди, кожна — посиланням із передоглядом. "
            "Натисніть на передогляд, щоб відкрити публікацію з коментарями.\n\n"
            "Натисніть «Виберіть канал» унизу, надішліть @username каналу чи посилання t.me або перешліть будь-яку його публікацію. Можна одразу кілька."
        ),
    },
    "add_prompt": {
        "en": "Tap “Choose a Channel” below, send a channel's @username or t.me link (several at once are fine), or forward any of its posts.",
        "ru": "Нажмите «Выбрать канал» внизу, пришлите @username канала или ссылку t.me (можно несколько сразу) либо перешлите любую его публикацию.",
        "uk": "Натисніть «Виберіть канал» унизу, надішліть @username каналу чи посилання t.me (можна кілька одразу) або перешліть будь-яку його публікацію.",
    },
    "help": {
        "en": (
            "New posts of the channels you choose come here, each as a link with a preview. "
            "Tap a preview to open the post with comments.\n\n"
            "/add — add a channel\n"
            "/channels — your channels: pause or remove\n"
            "/settings — notifications and language\n"
            "/stop — stop the bot and delete your list\n\n"
            "Only public channels can be added, up to {max}. The bot keeps your Telegram ID, language, settings "
            "and list of channels, nothing else."
        ),
        "ru": (
            "Новые публикации выбранных Вами каналов приходят сюда, каждая — ссылкой с предпросмотром. "
            "Нажмите на предпросмотр, чтобы открыть публикацию с комментариями.\n\n"
            "/add — добавить канал\n"
            "/channels — Ваши каналы: пауза или удаление\n"
            "/settings — уведомления и язык\n"
            "/stop — остановить бота и удалить Ваш список\n\n"
            "Добавить можно только публичные каналы, до {max}. Бот хранит Ваш Telegram ID, язык, настройки "
            "и список каналов, больше ничего."
        ),
        "uk": (
            "Нові публікації вибраних вами каналів надходять сюди, кожна — посиланням із передоглядом. "
            "Натисніть на передогляд, щоб відкрити публікацію з коментарями.\n\n"
            "/add — додати канал\n"
            "/channels — ваші канали: пауза або видалення\n"
            "/settings — сповіщення і мова\n"
            "/stop — зупинити бота й видалити ваш список\n\n"
            "Додати можна лише публічні канали, до {max}. Бот зберігає ваш Telegram ID, мову, налаштування "
            "і список каналів, більше нічого."
        ),
    },
    "added_one": {
        "en": "New posts from “{t}” will come here.",
        "ru": "Новые публикации канала «{t}» будут приходить сюда.",
        "uk": "Нові публікації каналу «{t}» надходитимуть сюди.",
    },
    "added_many": {
        "en": "New posts from these channels will come here: {t}.",
        "ru": "Новые публикации этих каналов будут приходить сюда: {t}.",
        "uk": "Нові публікації цих каналів надходитимуть сюди: {t}.",
    },
    "no_posts_yet": {
        "en": "“{t}” has no posts yet.",
        "ru": "В канале «{t}» пока нет публикаций.",
        "uk": "У каналі «{t}» ще немає публікацій.",
    },
    "queued": {
        "en": "{c} is in the queue: the bot reads up to {n} channels for all its users, and every place is taken. Its new posts will start coming here as soon as a place frees up.",
        "ru": "{c} в очереди: бот читает не больше {n} каналов на всех пользователей, и все места заняты. Новые публикации начнут приходить сюда, как только место освободится.",
        "uk": "{c} у черзі: бот читає не більше {n} каналів на всіх користувачів, і всі місця зайняті. Нові публікації почнуть надходити сюди, щойно звільниться місце.",
    },
    "already": {
        "en": "{c} is already in your list.",
        "ru": "{c} уже в Вашем списке.",
        "uk": "{c} уже у вашому списку.",
    },
    "not_channel": {
        "en": "{c} is not a public channel.",
        "ru": "{c} — не публичный канал.",
        "uk": "{c} — не публічний канал.",
    },
    "group": {
        "en": "{c} is a group. Only channels can be added.",
        "ru": "{c} — это группа. Добавить можно только канал.",
        "uk": "{c} — це група. Додати можна лише канал.",
    },
    "preview_off": {
        "en": "Telegram doesn't show the posts of {c} on the web, so the bot can't read them.",
        "ru": "Telegram не показывает публикации {c} в веб-версии, поэтому бот не может их читать.",
        "uk": "Telegram не показує публікації {c} у вебверсії, тому бот не може їх читати.",
    },
    "private": {
        "en": "This channel is private. Only public channels can be added.",
        "ru": "Это закрытый канал. Добавить можно только публичный.",
        "uk": "Це приватний канал. Додати можна лише публічний.",
    },
    "not_from_channel": {
        "en": "This message is not from a channel. Forward a post from a channel.",
        "ru": "Это сообщение не из канала. Перешлите публикацию из канала.",
        "uk": "Це повідомлення не з каналу. Перешліть публікацію з каналу.",
    },
    "bad_ref": {
        "en": "{c} is not a link to a public channel.",
        "ru": "{c} — не ссылка на публичный канал.",
        "uk": "{c} — не посилання на публічний канал.",
    },
    "limit_subs": {
        "en": "Your list already has {n} channels, the most it can hold.",
        "ru": "В Вашем списке уже {n} каналов — больше нельзя.",
        "uk": "У вашому списку вже {n} каналів — більше не можна.",
    },
    "limit_rate": {
        "en": "You can add up to {n} channels an hour. Try again later.",
        "ru": "Добавить можно не больше {n} каналов в час. Попробуйте позже.",
        "uk": "Додати можна не більше {n} каналів на годину. Спробуйте пізніше.",
    },
    "try_later": {
        "en": "Telegram's web view didn't answer, so {c} wasn't added. Please try again a bit later.",
        "ru": "Веб-версия Telegram не ответила, поэтому {c} не добавлен. Попробуйте ещё раз чуть позже.",
        "uk": "Вебверсія Telegram не відповіла, тому {c} не додано. Спробуйте ще раз трохи пізніше.",
    },
    "channels_head": {
        "en": "Channels: {n} of {max}.",
        "ru": "Каналы: {n} из {max}.",
        "uk": "Канали: {n} з {max}.",
    },
    "channels_empty": {
        "en": "Your list is empty.",
        "ru": "Ваш список пуст.",
        "uk": "Ваш список порожній.",
    },
    "found": {
        "en": "Channels found: {n}. Selected: {k}. Room left: {r}.",
        "ru": "Найдено каналов: {n}. Выбрано: {k}. Можно добавить ещё: {r}.",
        "uk": "Знайдено каналів: {n}. Вибрано: {k}. Можна додати ще: {r}.",
    },
    "too_many": {
        "en": "Selected {k}, but only {r} more fit. Untick {x}.",
        "ru": "Выбрано {k}, а поместится ещё {r}. Снимите галочки с {x}.",
        "uk": "Вибрано {k}, а вміститься ще {r}. Зніміть позначки з {x}.",
    },
    "checked_first": {
        "en": "The first {n} were checked; {k} more were not.",
        "ru": "Проверены первые {n}, ещё {k} не проверены.",
        "uk": "Перевірено перші {n}, ще {k} не перевірено.",
    },
    "not_checked": {
        "en": "{n} more were not checked.",
        "ru": "Ещё {n} не проверены.",
        "uk": "Ще {n} не перевірено.",
    },
    "room": {
        "en": "A list holds up to {n} channels, so {k} more were not checked.",
        "ru": "В список помещается до {n} каналов, поэтому ещё {k} не проверены.",
        "uk": "У список вміщується до {n} каналів, тому ще {k} не перевірено.",
    },
    "list_gone": {
        "en": "This list is out of date. Send it again.",
        "ru": "Этот список устарел. Пришлите его ещё раз.",
        "uk": "Цей список застарів. Надішліть його ще раз.",
    },
    "toast_removed": {"en": "Removed", "ru": "Удалено", "uk": "Видалено"},
    "toast_paused": {"en": "Paused", "ru": "На паузе", "uk": "На паузі"},
    "toast_resumed": {"en": "Resumed", "ru": "Возобновлено", "uk": "Продовжено"},
    "settings": {
        "en": "With notifications off, new posts arrive without sound.",
        "ru": "Когда уведомления отключены, новые публикации приходят без звука.",
        "uk": "Коли сповіщення вимкнено, нові публікації надходять без звуку.",
    },
    "stop_confirm": {
        "en": "Stop the bot and delete your list of channels?",
        "ru": "Остановить бота и удалить Ваш список каналов?",
        "uk": "Зупинити бота й видалити ваш список каналів?",
    },
    "stopped": {
        "en": "Your list is deleted. Send /start to begin again.",
        "ru": "Ваш список удалён. Чтобы начать заново, отправьте /start.",
        "uk": "Ваш список видалено. Щоб почати знову, надішліть /start.",
    },
    "web_off_removed": {
        "en": "Telegram no longer shows the posts of {c} on the web, so the bot can't read them. The channel is removed from your list.",
        "ru": "Telegram больше не показывает публикации {c} в веб-версии, поэтому бот не может их читать. Канал удалён из Вашего списка.",
        "uk": "Telegram більше не показує публікації {c} у вебверсії, тому бот не може їх читати. Канал видалено з вашого списку.",
    },
}

QUOTES = {"en": ("“", "”"), "ru": ("«", "»"), "uk": ("«", "»")}


def t(key: str, lang: str, **kw) -> str:
    text = T[key].get(lang) or T[key]["en"]
    return text.format(**kw) if kw else text


def quoted(titles: list[str], lang: str) -> str:
    a, b = QUOTES.get(lang, QUOTES["en"])
    return ", ".join(f"{a}{x}{b}" for x in titles)


# Every key in all three languages, and the same {placeholders} in each: checked by the tests.
assert all(set(v) == set(LANGS) for v in T.values())
