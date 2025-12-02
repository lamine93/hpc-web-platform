FROM python:3.11-slim

WORKDIR /app

# --- Dependencies & Tools ---
# Install OS packages (Node/npm, curl, jq, vim)
RUN apt-get update && \
    apt-get install -y nodejs npm curl jq vim && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies (Cache Layer 1)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Node dependencies (Cache Layer 2)
COPY package*.json .
RUN npm install

# --- Tailwind Compilation (Cache Invalidation Fix) ---
# Copy Tailwind config first
COPY tailwind.config.js .

# CRITICAL: Copy all source files (templates/JS) to bust cache on code change
COPY src/ ./src/ 

# Compile Tailwind CSS. Reruns if source code or config changes.
RUN npx tailwindcss -i ./src/static/css/src/input.css \
    -o ./src/static/css/dist/styles.css \
    --minify

# --- App Setup ---
# Create 'slurm' user and necessary directories
RUN groupadd -g 990 slurm && useradd -m -u 990 -g 990 slurm
RUN mkdir -p /data/slurm/users \
    && chown -R slurm:slurm /data/slurm
RUN mkdir -p /scratch && chmod 777 /scratch

# Copy remaining app files (e.g., main.py)
COPY . .

# Switch to non-root user
USER slurm

# Expose port and define startup command
EXPOSE 5000
CMD ["python", "main.py"]
