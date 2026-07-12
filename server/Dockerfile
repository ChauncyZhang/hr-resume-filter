FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/ux09
COPY server/requirements.txt /opt/ux09/server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY server /opt/ux09/server
USER 65532:65532
CMD ["uvicorn", "server.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
