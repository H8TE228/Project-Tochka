# Project-Tochka

## Установка

Установите зависимости приложения командой:

```sh
pip install -r requirements.txt
```

Создайте файл `.env` на основе `.env.example` и пропишите переменные окружения

```
# Пример
SECRET_KEY=<ключ>
DEBUG=True
DB_HOST=localhost
DB_PORT=5433
DB_USER=myuser
DB_PASS=mypassword
DB_NAME=mydatabase
```

Сгененировать ключ можно командой
```sh
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

Развернуть PostgreSQL можно из Docker
```sh
docker run --name my-postgres1 \
  -e POSTGRES_PASSWORD=mypassword \
  -e POSTGRES_USER=myuser \
  -e POSTGRES_DB=mydatabase \
  -p 5433:5432 \
  -d postgres:16
```

Применение миграций для БД
```sh
python manage.py migrate
```

## Запуск

```sh
python manage.py runserver
```
