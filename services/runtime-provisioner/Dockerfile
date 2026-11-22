FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 provisioner \
 && useradd --system --uid 10001 --gid provisioner --home-dir /app --create-home provisioner
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN mkdir -p /var/lib/suly-runtime/workspaces \
 && chmod 0700 /var/lib/suly-runtime /var/lib/suly-runtime/workspaces \
 && chown -R 10001:10001 /var/lib/suly-runtime /app
USER 10001:10001
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
