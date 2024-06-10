# ensembl-refget

# How to run
    cd nginx-unit
    python3.11 -m venv venv
    pip install -r ../requirements.txt
    export UNIT=$(docker run -d --mount type=bind,src=/mypath/nginx-unit,dst=/www/unit --mount type=bind,src=/mypath/data,dst=/www/unit/data -p 8001:8000 unit:1.32.1-python3.11)
    docker exec -ti $UNIT curl -X PUT --data-binary @/www/unit/service.conf --unix-socket /var/run/control.unit.sock http://localhost/config
    curl -X GET localhost:8001
    
