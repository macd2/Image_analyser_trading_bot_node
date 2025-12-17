# Multi-runtime: Node.js + Python 3.12
# Start with Python 3.12 slim image, then add Node.js
FROM python:3.12-slim AS base

# Install Node.js 20
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install remaining dependencies for native modules + PostgreSQL client + Playwright/Chromium dependencies + VNC
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    # Playwright/Chromium system dependencies
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    # VNC server dependencies (minimal - only Xvfb + x11vnc for login)
    xvfb \
    x11vnc \
    supervisor \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Enable corepack for pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Install Node.js dependencies
RUN pnpm install --frozen-lockfile

# Copy Python requirements and install
COPY python/requirements.txt ./python/
RUN python3 -m pip install --break-system-packages -r ./python/requirements.txt && \
    python3 -c "import boto3; print('✓ boto3 installed successfully')" || \
    (echo "ERROR: boto3 installation failed!" && exit 1)

# Install Playwright browsers (Chromium with minimal args for VNC)
# Set PLAYWRIGHT_BROWSERS_PATH to cache location
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.cache/playwright
RUN python3 -m playwright install chromium --with-deps

# Copy all source code
COPY . .

# Clean any stale build cache and build Next.js
RUN rm -rf .next && pnpm build

# Create data directories and log directories
RUN mkdir -p data/charts data/charts/.backup logs /var/log/supervisor

# Copy supervisor configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose ports
EXPOSE 3000
# Note: Port 5900 (x11vnc) exposed via Railway TCP Proxy, not Docker EXPOSE

# Set environment variables
ENV NODE_ENV=production
# PORT is set by Railway - don't hardcode it here
ENV DISPLAY=:99

# Start all services via supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

