FROM python:3.11-bookworm

RUN set -ex \
    && apt-get update \
    && apt-get install --no-install-recommends --no-install-suggests -y python3-tkrzw

WORKDIR /www/uvicorn

COPY app/requirements.txt /www/uvicorn/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /www/uvicorn/requirements.txt

COPY app/webapp/ /www/uvicorn/app

ENV PYTHONPATH=/usr/lib/python3/dist-packages/:/www/uvicorn/app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

EXPOSE 8000
