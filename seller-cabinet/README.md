# Seller Cabinet (B2B)

Микросервис кабинета продавца для NeoMarket. Управление товарами, SKU, накладными и категориями.

---

## Стек

- Python 3.12
- Django 5
- Django REST Framework
- PostgreSQL 16
- JWT

---

## Базовый URL

/api/v1/

---

## Аутентификация

```http
Authorization: Bearer <token>
```

Требуется роль: `seller`

---

## Эндпоинты (реализовано)


| Метод  | URL                       | Описание                  |
| ------ | ------------------------- | ------------------------- |
| GET    | `/api/v1/categories`      | Получить список категорий |
| POST   | `/api/v1/categories`      | Создать категорию         |
| GET    | `/api/v1/categories/{id}` | Получить категорию        |
| PUT    | `/api/v1/categories/{id}` | Обновить категорию        |
| DELETE | `/api/v1/categories/{id}` | Удалить категорию         |
| GET    | `/api/v1/products`        | Список товаров продавца   |
| POST   | `/api/v1/products`        | Создать товар             |
| GET    | `/api/v1/products/{id}`   | Получить товар            |
| PUT    | `/api/v1/products/{id}`   | Обновить товар            |
| POST   | `/api/v1/skus`            | Создать SKU               |
| PUT    | `/api/v1/skus/{id}`       | Обновить SKU              |
| DELETE | `/api/v1/skus/{id}`       | Удалить SKU (soft delete) |
| POST   | `/api/v1/invoices`        | Создать накладную         |
| POST   | `/api/v1/invoices/accept` | Принять накладную         |


### Сервисные вызовы (X-Service-Key)


| Метод | URL                         | Описание                                                             |
| ----- | --------------------------- | -------------------------------------------------------------------- |
| POST  | `/api/v1/reserve`           | Резервирование остатков под заказ                                    |
| POST  | `/api/v1/fulfill`           | Списание резерва при доставке (уменьшает только `reserved_quantity`) |
| POST  | `/api/v1/unreserve`         | Отмена резерва                                                       |
| POST  | `/api/v1/events/moderation` | Применение решения модерации                                         |


Заголовок: `X-Service-Key: <SERVICE_API_KEY>`.

---

# Примеры запросов

## Категории

### Создать категорию

```bash
curl -X POST http://localhost:8001/api/v1/categories \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Одежда"}'
```

---

## Товары

### Создать товар

```bash
curl -X POST http://localhost:8001/api/v1/products \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Футболка",
    "slug": "futbolka-black",
    "description": "Черная футболка",
    "category_id": "uuid",
    "images": [],
    "characteristics": []
  }'
```

---

### Получить список товаров (seller-cabinet)

Только товары текущего продавца (из JWT). Параметр `seller_id` в query **игнорируется**. Удалённые товары приходят с `deleted: true`. Поле `status` в ответе: `ACTIVE` | `BLOCKED` | `DELETED` (агрегат по `deleted` и внутреннему статусу).

**Пагинация:** `limit` (по умолчанию 20, макс. 100), `offset` (по умолчанию 0).

**Фильтры:** `status=ACTIVE|BLOCKED|DELETED` (без параметра — все свои товары, включая удалённые), `search` — подстрока в `title` без учёта регистра.

Ответ: `items`, `total`, `limit`, `offset`. В каждом элементе: `skus_count`, `total_active_quantity` (сумма `active_quantity` по SKU).

В JWT по желанию можно передать `seller_id` (UUID записи `Seller`) — он должен совпадать с продавцом, привязанным к `user_id` из того же токена.

```bash
curl "http://localhost:8001/api/v1/products?limit=20&offset=0&status=ACTIVE&search=phone" \
  -H "Authorization: Bearer <token>"
```

Пример тела ответа:

```json
{
  "items": [
    {
      "id": "uuid",
      "title": "Смартфон",
      "description": "...",
      "status": "ACTIVE",
      "deleted": false,
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z",
      "skus_count": 3,
      "total_active_quantity": 150
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

**Каталог B2C** по тому же пути: `GET /api/v1/products` с заголовком `X-Service-Key` (без Bearer) — другой формат ответа, без пагинации продавца.

---

## SKU

### Создать SKU

```bash
curl -X POST http://localhost:8001/api/v1/skus \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "uuid",
    "name": "XL",
    "price_cents": 1000,
    "active_quantity": 10,
    "is_enabled": true
  }'
```

---

### Обновить SKU

```bash
curl -X PUT http://localhost:8001/api/v1/skus/{id} \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "XXL",
    "price_cents": 1200,
    "active_quantity": 20
  }'
```

### Удалить SKU (soft delete)

Нельзя удалить SKU с ненулевым резервом (`reserved_quantity`). У товара в статусе `HARD_BLOCKED` удаление SKU запрещено (403). Если удалён последний SKU и товар был `ON_MODERATION`, товар переводится в `CREATED`, в Moderation уходит событие `DELETED`. Если товар `MODERATED` и у SKU был `active_quantity > 0`, в B2C отправляется `SKU_OUT_OF_STOCK`.

```bash
curl -X DELETE http://localhost:8001/api/v1/skus/{id} \
  -H "Authorization: Bearer <token>"
```

Успех: `200` и `{"ok": true, "message": "SKU deleted successfully"}`.

---

## Накладные

### Создать накладную

```bash
curl -X POST http://localhost:8001/api/v1/invoices \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "lines": [
      {"sku_id": "uuid", "quantity": 10}
    ]
  }'
```

---

### Принять накладную

```bash
curl -X POST http://localhost:8001/api/v1/invoices/accept \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "uuid"
  }'
```

---

## Fulfill (доставка заказа)

Сервис заказов вызывает после фактической отгрузки: списывается только резерв, свободный остаток (`active_quantity`) не меняется. Повтор с тем же `order_id` безопасен (идемпотентность).

```bash
curl -X POST http://localhost:8001/api/v1/fulfill \
  -H "X-Service-Key: <service-api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "uuid",
    "sku_id": "uuid",
    "quantity": 1
  }'
```

---

## Запуск

```bash
docker compose up --build
```

Сервис: [http://localhost:8001](http://localhost:8001)