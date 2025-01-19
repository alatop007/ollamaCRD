FROM python:3.9-slim
RUN pip install kopf kubernetes
WORKDIR /app
COPY controller.py .
CMD ["kopf", "run", "--standalone", "controller.py"]