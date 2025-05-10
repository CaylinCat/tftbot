# Use official Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install only necessary system dependencies (minimal for Flask, aiohttp, etc.)
RUN apt-get update && apt-get install -y \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy app files to container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (for Flask keep_alive server)
EXPOSE 5000

# Start the bot
CMD ["python", "bot.py"]