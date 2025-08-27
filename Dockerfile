FROM python:3.11-slim

# Install system dependencies and add Google Cloud SDK repo
RUN apt-get update && apt-get install -y curl apt-transport-https ca-certificates gnupg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
       | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
       | gpg --dearmor > /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y \
       chromium \
       chromium-driver \
       graphviz \
       unzip \
       google-cloud-sdk \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PATH="/usr/lib/google-cloud-sdk/bin:$PATH"

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app

# Set entrypoint for Cloud Run Job
ENTRYPOINT ["python", "app/main.py"]
