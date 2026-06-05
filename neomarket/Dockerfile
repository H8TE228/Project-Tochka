FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev dos2unix \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY neomarket .

RUN dos2unix neomarket/entrypoint.sh && chmod +x neomarket/entrypoint.sh

ENTRYPOINT ["neomarket/entrypoint.sh"]

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
