FROM python:3.12

COPY requirements.txt /app/requirements.txt

WORKDIR /app
RUN pip install -r requirements.txt

COPY main.py /app
COPY kandinsky.py /app
COPY .env /app

CMD ["python", "main.py"]
