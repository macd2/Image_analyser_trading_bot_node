# Multi-runtime: Node.js + Python
FROM node:20-slim AS base

# Install Python and dependencies for native modules + PostgreSQL client
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    libpq-dev \
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

# Copy all source code
COPY . .

# Build Next.js
RUN pnpm build

# Create data directories
RUN mkdir -p data/charts data/charts/.backup logs

# Expose port
EXPOSE 3000

# Set environment
ENV NODE_ENV=production
ENV PORT=3000

# Start the server
CMD ["pnpm", "start"]

