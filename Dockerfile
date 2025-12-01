FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (schema is now in app/schema/)
COPY . .

# Expose port (documentation - actual port from env var)
EXPOSE 7860

# Run application
CMD ["python", "app.py"]

