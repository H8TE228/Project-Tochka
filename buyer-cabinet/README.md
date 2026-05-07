# Buyer Cabinet (B2C)

Микросервис витрины покупателя для NeoMarket.

## Зона ответственности

- публичная витрина и карточки товаров;
- корзина покупателя;
- избранное;
- подписки на наличие и скидки;
- баннеры, коллекции и рекомендации;
- заказы покупателя.

## Локальный запуск

Создайте `.env` на основе `.env.example`.

```bash
source ../.venv/bin/activate
python manage.py migrate
python manage.py runserver 8003
```

## Запуск в Docker

```bash
docker compose up --build
```

Сервис будет доступен на `http://localhost:8003`.
В общем Docker Compose `buyer-cabinet` будет обращаться к B2B по имени сервиса: `http://seller-cabinet:8001`.

Для быстрой локальной проверки без PostgreSQL можно временно использовать SQLite:

```bash
USE_SQLITE=True SECRET_KEY=test-secret python manage.py check
USE_SQLITE=True SECRET_KEY=test-secret python manage.py test storefront
```

## Проверка

```bash
curl http://localhost:8003/api/v1/health
```
