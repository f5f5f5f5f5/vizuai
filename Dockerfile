FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /ms-playwright && python -m playwright install --with-deps chromium

RUN addgroup --system app && adduser --system --ingroup app app

COPY --chown=app:app . /app
RUN chown -R app:app /ms-playwright

USER app
CMD ["python", "main.py"]
