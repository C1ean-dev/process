FROM python:3.9-slim-buster

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y tesseract-ocr poppler-utils ghostscript
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["flask", "run", "--host=0.0.0.0"]
