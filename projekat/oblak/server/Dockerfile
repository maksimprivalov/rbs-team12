FROM python:3.11-slim

WORKDIR /app

# e2fsprogs — za debugfs (inject koda u Firecracker ext4 image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    e2fsprogs \
    && rm -rf /var/lib/apt/lists/*

# Firecracker binarni fajl
# Montira se iz /opt/firecracker na hostu (setup-firecracker.sh)
# Ako nije dostupan, server automatski koristi subprocess sandbox
ENV FIRECRACKER_BIN=/usr/local/bin/firecracker
RUN if [ -f /opt/firecracker/firecracker ]; then \
        ln -sf /opt/firecracker/firecracker /usr/local/bin/firecracker; \
    fi

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
