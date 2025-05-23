ARG NAUTOBOT_VERSION
ARG PYTHON_VER
FROM ghcr.io/nautobot/nautobot:${NAUTOBOT_VERSION}-py${PYTHON_VER} as nautobot-base
#FROM ghcr.io/nautobot/nautobot:2.3.16-py${PYTHON_VER} as nautobot-base

USER 0

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get autoremove -y && \
    apt-get clean all && \
    rm -rf /var/lib/apt/lists/* && \
    pip --no-cache-dir install --upgrade pip wheel

FROM ghcr.io/nautobot/nautobot-dev:${NAUTOBOT_VERSION}-py${PYTHON_VER} as builder

CMD ["nautobot-server", "runserver", "0.0.0.0:8080", "--insecure"]

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get autoremove -y && \
    apt-get clean all && \
    rm -rf /var/lib/apt/lists/*

COPY ../pyproject.toml ../poetry.lock /source/
COPY ../plugins /source/plugins
# COPY ../packages /source/packages

# Install the nautobot project to include Nautobot
RUN cd /source && \
    poetry install --no-interaction --no-ansi && \
    mkdir /tmp/dist && \
    poetry export --without-hashes -o /tmp/dist/requirements.txt

# -------------------------------------------------------------------------------------
# Build Apps in plugins folder
# -------------------------------------------------------------------------------------
# RUN for plugin in /source/plugins/*; do \
#         cd $plugin && \
#         poetry build && \
#         cp dist/*.whl /tmp/dist; \
#     done


#COPY ../jobs /opt/nautobot/jobs
# COPY ../metrics /opt/nautobot/metrics
COPY ../config/nautobot_config.py /opt/nautobot/nautobot_config.py



WORKDIR /source

###################################

# -------------------------------------------------------------------------------------
# Final Image
# -------------------------------------------------------------------------------------
FROM nautobot-base as nautobot

ARG PYTHON_VER
# Copy from base the required python libraries and binaries
COPY --from=builder /tmp/dist /tmp/dist
COPY --from=builder /opt/nautobot /opt/nautobot
COPY --from=builder /usr/local/lib/python${PYTHON_VER}/site-packages /usr/local/lib/python${PYTHON_VER}/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
# COPY ../packages /source/packages


# Verify that pyuwsgi was installed correctly, i.e. with SSL support
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN pyuwsgi --cflags | sed 's/ /\n/g' | grep -e "^-DUWSGI_SSL$"

###### JOBS #######

COPY config/uwsgi.ini /opt/nautobot/uwsgi.ini
RUN chmod 644 /opt/nautobot/uwsgi.ini

USER root

RUN mkdir -p /opt/nautobot/jobs && chown -R nautobot:nautobot /opt/nautobot/jobs

COPY --chown=nautobot:nautobot ../jobs /opt/nautobot/jobs

RUN chmod -R 755 /opt/nautobot/jobs
RUN chmod 644 /opt/nautobot/jobs/__init__.py

USER nautobot


#####################

#RUN sed -i 's/^processes = .*/processes = 5/' /opt/nautobot/uwsgi.ini && \
#    sed -i 's/^listen = .*/listen = 256/' /opt/nautobot/uwsgi.ini && \
#    sed -i 's/^buffer-size = .*/buffer-size = 8192/' /opt/nautobot/uwsgi.ini
#
#CMD ["uwsgi", "--ini", "/opt/nautobot/uwsgi.ini"]



