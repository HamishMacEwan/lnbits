FROM python:3.7-slim

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -q -r requirements.txt
RUN pip install --no-cache-dir -q hypercorn
COPY . /app

EXPOSE 5000
