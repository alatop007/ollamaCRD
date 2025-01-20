FROM python:3.9-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install kopf kubernetes
COPY controller.py .
# Stage 2
FROM scratch
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=builder /usr/local/bin/python /usr/local/bin/python
COPY --from=builder /app/controller.py /app/controller.py
WORKDIR /app
CMD ["/usr/local/bin/python", "-m", "kopf", "run", "--standalone", "controller.py"]
