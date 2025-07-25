# Финансовый помощник - Telegram Bot

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-blue.svg)](https://docs.aiogram.dev/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

Финансовый помощник - это умный Telegram-бот для управления личными финансами. Он помогает отслеживать доходы и расходы, анализировать финансовые привычки и даёт персональные советы по оптимизации бюджета.

## 🌟 Основные возможности

- **Учет операций**: Добавление доходов и расходов по категориям
- **Финансовая аналитика**: Автоматические отчеты и анализ расходов
- **Персональные советы**: Рекомендации по экономии и оптимизации бюджета
- **Курсы валют**: Актуальные курсы основных валют
- **Баланс**: Отслеживание текущего финансового состояния
- **Категоризация**: Гибкая система категорий для расходов

## 🛠 Технологический стек

- **Python 3.10+** - основной язык программирования
- **aiogram 3.x** - фреймворк для создания Telegram ботов
- **aiosqlite** - асинхронная работа с SQLite базой данных
- **aiohttp** - асинхронные HTTP-запросы для получения курсов валют
- **dotenv** - управление переменными окружения
- **logging** - система логирования операций

## ⚙️ Установка и настройка

### Предварительные требования
- Python 3.10 или новее
- Аккаунт Telegram
- Токен для Telegram бота (получить у [@BotFather](https://t.me/BotFather))

### Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/ваш-пользователь/финансовый-помощник.git
cd финансовый-помощник
```

2. Установите зависимости:
```bash
pip install aiogram aiosqlite aiohttp python-dotenv
```

3. Создайте файл `.env` в корневой директории проекта и добавьте:
```env
BOT_TOKEN=ваш_токен_бота
EXCHANGE_API_KEY=ваш_ключ_api_для_валют
```

### Настройка базы данных
База данных SQLite будет создана автоматически при первом запуске бота в файле `finance.db`.

## 🚀 Запуск бота

```bash
python bot.py
```

## 🎮 Использование бота

1. Начните работу с командой `/start`
2. Используйте меню для навигации:
   - **📊 Мои финансы** - просмотр баланса и отчетов
   - **💱 Курс валют** - актуальные курсы валют
   - **💡 Советы** - персональные финансовые советы
   - **➕ Добавить операцию** - добавление новой транзакции

3. Для добавления операции:
   - Выберите тип операции (доход/расход)
   - Выберите категорию
   - Введите сумму
   - Добавьте комментарий (опционально)

## 📊 Примеры работы

### Главное меню
![Главное меню](https://via.placeholder.com/300x600?text=Главное+меню+бота)

### Финансовый отчет
```text
📈 Финансовый отчет за месяц:

⬆️ 🍔 Еда: +15000.00 ₽
⬇️ 🏠 Жилье: -25000.00 ₽
⬇️ 🚕 Транспорт: -5000.00 ₽

📊 Итого:
Доходы: +15000.00 ₽
Расходы: -30000.00 ₽
Баланс: -15000.00 ₽

💡 Анализ:
Сбережения: -100.0% от доходов
Рекомендация: Попробуйте сократить расходы на развлечения и питание вне дома
```

### Курсы валют
```text
💱 Актуальные курсы к USD:

🇺🇸 Доллар США: 1.00
🇪🇺 Евро: 0.92
🇨🇳 Китайский юань: 7.23
🇬🇧 Фунт стерлингов: 0.79

🇷🇺 Российский рубль: 92.45
🇪🇺 Евро в рублях: 100.50
🇬🇧 Фунт стерлингов в рублях: 117.03
🇨🇳 Китайский юань в рублях: 12.78

Курсы обновляются ежедневно в 12:00 МСК
```

## 📝 Лицензия

Этот проект распространяется под лицензией MIT. Подробнее см. в файле [LICENSE](LICENSE).

