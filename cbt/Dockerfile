FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Copy frontend files into a static directory the server can serve
COPY login.html   /app/static/login.html
COPY admin.html   /app/static/admin.html
COPY student.html /app/static/student.html

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
