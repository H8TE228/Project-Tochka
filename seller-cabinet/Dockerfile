FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev dos2unix \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Подстраховка: убираем CRLF, которые могли попасть из Windows
RUN dos2unix seller_cabinet/entrypoint.sh && chmod +x seller_cabinet/entrypoint.sh

ENTRYPOINT ["seller_cabinet/entrypoint.sh"]

EXPOSE 8001
CMD ["python", "manage.py", "runserver", "0.0.0.0:8001"]