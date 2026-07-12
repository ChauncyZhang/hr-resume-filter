FROM python:3.12.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/ux09
COPY server/requirements.txt /opt/ux09/server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY server /opt/ux09/server
USER 65532:65532
CMD ["uvicorn", "server.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test
USER root
COPY server/requirements-dev.txt /opt/ux09/server/requirements-dev.txt
RUN pip install --no-cache-dir -r server/requirements-dev.txt
CMD ["python", "-m", "pytest", "server/tests", "-q"]
