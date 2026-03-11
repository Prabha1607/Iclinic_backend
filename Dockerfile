FROM python:3.13   

WORKDIR /app


RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.api.rest.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
