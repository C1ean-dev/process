FROM python:3.9-slim-buster

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y tesseract-ocr poppler-utils ghostscript
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

ENV FLASK_APP=app/__init__.py
ENV FLASK_DEBUG=1
ENV SQLALCHEMY_DATABASE_URI=sqlite:///site.db

CMD ["flask", "run", "--host=0.0.0.00", "--port=8080"]
