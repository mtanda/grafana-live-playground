FROM python:3.12-slim
RUN pip install --no-cache-dir websockets==14.1
COPY generate.py /app/generate.py
CMD ["python", "-u", "/app/generate.py"]
