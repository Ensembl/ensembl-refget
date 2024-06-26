FROM unit:1.32.1-python3.11

WORKDIR /www/unit/

RUN set -ex \
    && echo 'deb http://deb.debian.org/debian bookworm main contrib' >> /etc/apt/sources.list.d/bookworm.list \
    && apt-get update \
    && apt-get install --no-install-recommends --no-install-suggests -y python3-tkrzw python3-fastapi python3-cachetools python3-pydantic

COPY app/requirements.txt /config/requirements.txt
RUN python3 -m pip install -r /config/requirements.txt

COPY app/webapp/ /www/unit/
RUN chown -R unit:unit /www/unit

COPY app/config/config.json /docker-entrypoint.d/.unit.conf.json

# export UNIT=$(docker run -d --mount type=bind,src=/mypath/nginx-unit,dst=/www/unit --mount type=bind,src=/mypath/data,dst=/www/unit/data -p 8001:8000 unit:1.32.1-python3.11)
# docker exec -ti $UNIT curl -X PUT --data-binary @/www/unit/service.conf --unix-socket /var/run/control.unit.sock http://localhost/config

CMD ["unitd", "--no-daemon", "--control", "unix:/var/run/control.unit.sock"]

EXPOSE 8001
