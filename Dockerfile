FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first (optional optimization for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Set working directory to the script folder
WORKDIR /app/src

# Run the application
CMD ["python", "telegram.py"]
