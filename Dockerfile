FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy schema file first (explicitly, to ensure it's included)
COPY plan/schema/schema.yaml plan/schema/schema.yaml

# Copy application code
COPY . .

# Expose port (documentation - actual port from env var)
EXPOSE 7860

# Run application
CMD ["python", "app.py"]

