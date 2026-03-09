FROM python:3.13-trixie

RUN set -ex \
    && apt-get update \
    && apt-get install --no-install-recommends --no-install-suggests -y python3-tkrzw

COPY . /www/uvicorn/

WORKDIR /www/uvicorn/api
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/usr/lib/python3/dist-packages/:/www/uvicorn/api/src/

WORKDIR /www/uvicorn/api/src/refget

CMD ["uvicorn", "main:app", \
    "--host", "0.0.0.0", \
    "--port", "8000", \
    "--log-config", "logconfig.yaml", \
    "--workers", "2"]

EXPOSE 8000
