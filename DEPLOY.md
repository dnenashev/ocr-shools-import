# Деплой на Render

Инструкция по развертыванию OCR CRM на Render.com

## Подготовка

1. Убедитесь что ваш код загружен в Git репозиторий (GitHub, GitLab, Bitbucket)
2. Зарегистрируйтесь на [Render.com](https://render.com)

## Создание Web Service на Render

### Вариант 1: Через Render Dashboard

1. Зайдите в Render Dashboard
2. Нажмите "New +" → "Web Service"
3. Подключите ваш Git репозиторий
4. Заполните настройки:
   - **Name**: `ocr-crm`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Starter (или выше)

### Вариант 2: Через render.yaml (рекомендуется)

1. Используйте файл `render.yaml` из корня проекта
2. В Render Dashboard: "New +" → "Blueprint"
3. Подключите репозиторий с `render.yaml`
4. Render автоматически создаст сервис с нужными настройками

## Настройка переменных окружения

В Render Dashboard → Environment Variables добавьте:

### Обязательные переменные:

```
OPENROUTER_API_KEY=your_openrouter_api_key
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGODB_DB_NAME=ocr_crm
ADMIN_PASSWORD=your_secure_password
SECRET_KEY=your_secret_key_for_sessions
```

### AMO CRM переменные:

```
AMO_SECRET_KEY=your_amo_secret_key
AMO_REDIRECT_URI=https://yoursubdomain.amocrm.ru
INTEGRATION_ID=your_integration_id
AMO_LONG_TOKEN=your_long_token_jwt
AMO_SHORT_KEY=your_short_refresh_key
```

### Опциональные:

```
HOST=0.0.0.0
PORT=8000  # Render автоматически устанавливает PORT
```

## Важные замечания

### 1. Файловая система Render

⚠️ **ВНИМАНИЕ**: На Render файловая система **эфемерная** (ephemeral). Это значит:
- Файлы в папке `uploads/` будут удаляться при каждом деплое
- Для хранения изображений используйте:
  - **MongoDB GridFS** (рекомендуется)
  - **AWS S3** или другой cloud storage
  - **Render Disk** (платная опция, но файлы сохраняются)

### 2. Рекомендация: Использовать GridFS для изображений

Для production лучше хранить изображения в MongoDB GridFS вместо локальной файловой системы.

### 3. CORS настройки

В `backend/main.py` CORS настроен на `allow_origins=["*"]`. Для production укажите конкретные домены:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Проверка деплоя

После деплоя проверьте:

1. Health check: `https://your-app.onrender.com/health`
2. Главная страница: `https://your-app.onrender.com/`
3. Админ-панель: `https://your-app.onrender.com/admin`
4. API документация: `https://your-app.onrender.com/docs`

## Автоматический деплой

Render автоматически деплоит при каждом push в основную ветку (обычно `main` или `master`).

## Мониторинг

- Логи доступны в Render Dashboard → Logs
- Метрики в разделе Metrics
- Настройте алерты для ошибок

## Troubleshooting

### Проблема: Приложение не запускается

1. Проверьте логи в Render Dashboard
2. Убедитесь что все переменные окружения установлены
3. Проверьте что MongoDB доступна из Render

### Проблема: Ошибки подключения к MongoDB

1. Убедитесь что в MongoDB Atlas разрешён доступ с IP Render
2. Добавьте `0.0.0.0/0` в Network Access (для тестирования)
3. Проверьте формат строки подключения

### Проблема: Файлы не сохраняются

Это нормально для Render - используйте GridFS или cloud storage для production.

## Обновление приложения

Просто сделайте `git push` в основную ветку - Render автоматически задеплоит обновления.

