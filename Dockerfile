# Use Python 3.8 slim image as base
FROM python:3.8-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create static directory if it doesn't exist
RUN mkdir -p static

# Expose the port the app runs on
EXPOSE 5050

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5050"]