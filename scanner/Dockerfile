FROM python:3.12-slim
RUN groupadd -g 1001 fim && useradd -u 1001 -g fim -M -s /usr/sbin/nologin fim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /var/log/fim && chown -R 1001:1001 /var/log/fim /app
USER 1001:1001
CMD ["python", "main.py"]
