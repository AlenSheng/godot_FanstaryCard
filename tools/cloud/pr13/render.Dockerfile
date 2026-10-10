ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER root
RUN apt-get -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 -o Acquire::Retries=0 update \
    && apt-get -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 -o Acquire::Retries=0 install -y --no-install-recommends \
    xvfb xauth libgl1-mesa-dri libglx-mesa0 \
    && rm -rf /var/lib/apt/lists/*
ENV LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe LP_NUM_THREADS=1
USER 1000:1000
WORKDIR /work
