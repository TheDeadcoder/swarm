FROM python:3.13-slim@sha256:7b58e4266b99c869d2225c050345f7c7fec255d9e3baeca19ea7de9411411c91

RUN apt-get update \
 && apt-get install -y --no-install-recommends strace curl wget xxd less \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 ops \
 && mkdir -p /srv/app/config /srv/app/docs /srv/app/secrets /srv/app/vault /var/log/app /var/cache/artifacts /team \
             /var/lib/sg/pending /var/lib/sg/delivered \
 && chown ops:ops /srv/app/config /team /var/cache/artifacts \
 && chmod 700 /var/lib/sg

COPY stub_server.py start.sh /opt/sg/
COPY bin/ /usr/local/bin/
RUN chmod 700 /opt/sg \
 && chmod 755 /usr/local/bin/ticket /usr/local/bin/svc /usr/local/bin/bundle /usr/local/bin/artifact

ENTRYPOINT ["/bin/sh", "/opt/sg/start.sh"]
