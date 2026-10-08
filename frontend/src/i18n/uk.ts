// All user-facing strings live here so another locale can be added later.
export const uk = {
  appName: "NewsDigest",
  tagline: "AI-дайджест новин за вашими темами — прямо в Telegram",

  common: {
    loading: "Завантаження…",
    save: "Зберегти",
    saving: "Збереження…",
    cancel: "Скасувати",
    delete: "Видалити",
    edit: "Редагувати",
    back: "Назад",
    retry: "Спробувати ще раз",
    close: "Закрити",
    add: "Додати",
    remove: "Прибрати",
    never: "ще не було",
    unknownError: "Щось пішло не так. Спробуйте ще раз.",
    networkError: "Немає зв'язку з сервером. Перевірте з'єднання.",
  },

  nav: {
    topics: "Теми",
    settings: "Налаштування",
    logout: "Вийти",
    themeLight: "Світла тема",
    themeDark: "Темна тема",
    themeSystem: "Як у системі",
  },

  auth: {
    loginTitle: "Вхід",
    loginSubtitle: "Раді бачити вас знову",
    registerTitle: "Реєстрація",
    registerSubtitle: "Створіть акаунт і першу тему за хвилину",
    email: "Email",
    password: "Пароль",
    passwordConfirm: "Повторіть пароль",
    passwordHint: "Щонайменше 8 символів",
    loginButton: "Увійти",
    registerButton: "Зареєструватися",
    noAccount: "Ще немає акаунта?",
    haveAccount: "Вже маєте акаунт?",
    toRegister: "Зареєструватися",
    toLogin: "Увійти",
    errors: {
      emailRequired: "Вкажіть email",
      emailInvalid: "Некоректний email",
      passwordRequired: "Вкажіть пароль",
      passwordShort: "Пароль має містити щонайменше 8 символів",
      passwordMismatch: "Паролі не збігаються",
    },
  },

  apiErrors: {
    invalid_credentials: "Невірний email або пароль",
    email_taken: "Користувач з таким email вже існує",
    rate_limited: "Забагато спроб. Зачекайте хвилину і спробуйте знову.",
    csrf_failed: "Сесія застаріла. Оновіть сторінку.",
    not_authenticated: "Потрібно увійти",
    topic_limit_reached: "Досягнуто ліміту тем для акаунта",
    not_found: "Не знайдено",
    validation: "Перевірте правильність заповнення полів",
    telegram_not_configured: "Telegram-бот не налаштований на сервері",
  } as Record<string, string>,

  dashboard: {
    title: "Ваші теми",
    newTopic: "Нова тема",
    emptyTitle: "Поки що жодної теми",
    emptyText:
      "Опишіть, що вас цікавить, звичайними словами — ми знайдемо свіжі новини, відфільтруємо шум і надішлемо короткий дайджест.",
    emptyCta: "Створити першу тему",
    nextRun: "Наступна розсилка",
    lastRun: "Остання перевірка",
    digests: (n: number) => `${n} ${plural(n, "дайджест", "дайджести", "дайджестів")}`,
    active: "Активна",
    paused: "На паузі",
    history: "Історія",
    limit: (n: number, max: number) => `${n} з ${max} тем`,
    loadError: "Не вдалося завантажити теми",
  },

  telegram: {
    bannerTitle: "Підключіть Telegram",
    bannerText: "Дайджести приходять у Telegram. Підключення займає один клік.",
    connect: "Підключити Telegram",
    connecting: "Відкриваємо Telegram…",
    waiting: "Очікуємо підтвердження в Telegram… Натисніть «Start» у боті.",
    openAgain: "Відкрити бота ще раз",
    connected: "Telegram підключено",
    connectedAs: (name: string) => `Підключено як @${name}`,
    notConnected: "Telegram не підключено",
    blocked:
      "Бот був заблокований у Telegram, тому розсилку зупинено. Розблокуйте бота і підключіть знову.",
    disconnect: "Відключити",
    fakeMode:
      "Сервер працює без токена Telegram-бота (fake-режим): дайджести зберігаються лише в історії на сайті.",
  },

  topic: {
    newTitle: "Нова тема",
    editTitle: "Тема",
    name: "Назва",
    namePlaceholder: "Наприклад: Криптовалюти",
    description: "Що саме вас цікавить",
    descriptionPlaceholder:
      "Опишіть природною мовою: «Криптовалюти: ціни BTC/ETH, регулювання, великі злами бірж»",
    descriptionHint: "Чим конкретніше опис, тим точніший фільтр релевантності.",
    language: "Мова дайджесту",
    frequency: "Частота",
    sendHour: "Година розсилки",
    weekday: "День тижня",
    timezoneNote: (tz: string) => `Час у вашому часовому поясі: ${tz}`,
    threshold: "Поріг релевантності",
    thresholdHint: "Вище — менше, але точніші новини.",
    advanced: "Додатково",
    create: "Створити тему",
    creating: "Створюємо і генеруємо запити…",
    saved: "Збережено",
    sendNow: "Надіслати зараз",
    sending: "Ставимо в чергу…",
    sendQueued: "Запущено. Результат з'явиться в історії за хвилину.",
    pause: "Пауза",
    resume: "Відновити",
    deleteConfirm: "Видалити тему разом з історією дайджестів?",
    queriesTitle: "Пошукові запити",
    queriesHint:
      "Згенеровані автоматично з опису. Можна змінити: ми шукаємо новини саме за цими запитами.",
    queriesEmpty: "Запитів немає — додайте хоча б один.",
    queryPlaceholder: "Новий запит",
    regenerate: "Згенерувати заново",
    regenerating: "Генеруємо…",
    saveQueries: "Зберегти запити",
    source: { google_news: "Google News", tavily: "Tavily" } as Record<string, string>,
    lastStatus: "Останній запуск",
    nextRun: "Наступна розсилка",
    viewHistory: "Історія дайджестів",
    notFound: "Тему не знайдено",
    errors: {
      nameRequired: "Вкажіть назву",
      descriptionShort: "Опишіть тему детальніше (щонайменше 3 символи)",
    },
  },

  frequency: {
    hourly: "Щогодини",
    "6h": "Кожні 6 годин",
    daily: "Щодня",
    weekly: "Щотижня",
  } as Record<string, string>,

  runStatus: {
    queued: "у черзі",
    empty: "нових новин немає",
    sent: "надіслано",
    fake_sent: "збережено (fake Telegram)",
    no_chat: "Telegram не підключено",
    failed: "помилка надсилання",
    error: "помилка обробки",
  } as Record<string, string>,

  weekdays: ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"],

  history: {
    title: "Історія дайджестів",
    empty: "Дайджестів ще не було",
    emptyText:
      "Коли з'являться нові релевантні новини, дайджест буде тут. Можна запустити перевірку вручну.",
    articles: (n: number) => `${n} ${plural(n, "новина", "новини", "новин")}`,
    expand: "Показати",
    collapse: "Згорнути",
    status: {
      sent: "Надіслано",
      fake_sent: "Збережено (fake Telegram)",
      no_chat: "Не надіслано: Telegram не підключено",
      failed: "Помилка надсилання",
    } as Record<string, string>,
  },

  settings: {
    title: "Налаштування",
    account: "Акаунт",
    timezone: "Часовий пояс",
    timezoneHint: "Від нього залежить час щоденних і щотижневих розсилок.",
    telegram: "Telegram",
    appearance: "Вигляд",
    theme: "Тема оформлення",
    logout: "Вийти з акаунта",
    saved: "Збережено",
  },

  notFound: {
    title: "Сторінку не знайдено",
    back: "На головну",
  },
};

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

export const t = uk;
