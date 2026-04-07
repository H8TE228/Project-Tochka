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

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/v1/categories` | Получить список категорий |
| POST | `/api/v1/categories` | Создать категорию |
| GET | `/api/v1/categories/{id}` | Получить категорию |
| PUT | `/api/v1/categories/{id}` | Обновить категорию |
| DELETE | `/api/v1/categories/{id}` | Удалить категорию |
| GET | `/api/v1/products` | Список товаров продавца |
| POST | `/api/v1/products` | Создать товар |
| GET | `/api/v1/products/{id}` | Получить товар |
| PUT | `/api/v1/products/{id}` | Обновить товар |
| POST | `/api/v1/skus` | Создать SKU |
| PUT | `/api/v1/skus/{id}` | Обновить SKU |
| POST | `/api/v1/invoices` | Создать накладную |
| POST | `/api/v1/invoices/accept` | Принять накладную |

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

### Получить список товаров
```bash
curl http://localhost:8001/api/v1/products \
  -H "Authorization: Bearer <token>"
```

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

## Запуск

```bash
docker compose up --build
```

Сервис: http://localhost:8001
