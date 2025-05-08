# Use official Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# System dependencies needed for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libxshmfence1 \
    libatk1.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libu2f-udev \
    libvulkan1 \
    fonts-liberation \
    libappindicator3-1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy app files to container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN python -m playwright install

# Expose port (if Flask is used)
EXPOSE 5000

# Start command (modify if you only want to run bot or Flask)
CMD ["python", "bot.py"]