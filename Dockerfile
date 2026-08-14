ARG CMCLOUD_BASE_IMAGE=ghcr.io/lyj0309/docker-wine-vnc:latest
FROM ${CMCLOUD_BASE_IMAGE}

COPY root/ /

RUN chmod 755 /usr /usr/local /usr/local/bin /defaults /custom-cont-init.d \
    && chmod 755 /defaults/autostart /usr/local/bin/*.sh /usr/local/bin/*.py /custom-cont-init.d/*.sh
