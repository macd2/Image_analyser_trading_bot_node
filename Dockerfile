# Multi-runtime: Node.js + Python
FROM node:20-slim AS base

# Install Python and dependencies for native modules + PostgreSQL client + Playwright/Chromium dependencies + VNC
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
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
    # VNC server dependencies
    xvfb \
    x11vnc \
    fluxbox \
    supervisor \
    net-tools \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

# Enable corepack for pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Install Node.js dependencies
RUN pnpm install --frozen-lockfile

# Copy Python requirements and install
COPY python/requirements.txt ./python/
RUN python3 -m pip install --break-system-packages -r python/requirements.txt

# Install Playwright browsers (Chromium) with dependencies
# Set PLAYWRIGHT_BROWSERS_PATH to cache location
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.cache/playwright
RUN python3 -m playwright install chromium --with-deps

# Install noVNC for web-based VNC access
RUN wget -qO- https://github.com/novnc/noVNC/archive/v1.4.0.tar.gz | tar xz -C /opt && \
    mv /opt/noVNC-1.4.0 /opt/noVNC && \
    ln -s /opt/noVNC/vnc.html /opt/noVNC/index.html && \
    wget -qO- https://github.com/novnc/websockify/archive/v0.11.0.tar.gz | tar xz -C /opt && \
    mv /opt/websockify-0.11.0 /opt/websockify

# Copy all source code
COPY . .

# Build Next.js
RUN pnpm build

# Create data directories and log directories
RUN mkdir -p data/charts data/charts/.backup logs /var/log/supervisor

# Copy supervisor configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose ports
EXPOSE 3000
EXPOSE 6080

# Set environment variables
ENV NODE_ENV=production
ENV PORT=3000
ENV DISPLAY=:99

# Start all services via supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

