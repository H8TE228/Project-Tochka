# Seller Cabinet (B2B)

Микросервис кабинета продавца для NeoMarket. Управление товарами, SKU.

## Стек

- Python 3.12 / Django 5 / Django REST Framework
- PostgreSQL 16

## Эндпоинты (реализовано)

| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/api/v1/products` | Создать товар |
| GET | `/api/v1/products/{id}` | Получить товар со всеми SKU |
| PUT | `/api/v1/products/{id}` | Изменить товар |
| POST | `/api/v1/skus` | Создать SKU |

## Аутентификация

JWT-токен из auth-сервиса передаётся в заголовке `Authorization: Bearer <token>`.  
`GET /api/v1/products/{id}` — публичный, остальные — только для роли `seller`.

## Запуск

```bash
cp .env.example .env
# Заполнить SECRET_KEY (тот же, что у auth-сервиса)
docker compose up --build
```

Сервис поднимается на `http://localhost:8001`.
