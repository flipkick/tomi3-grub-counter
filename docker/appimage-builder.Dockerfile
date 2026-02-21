FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    ca-certificates \
    curl \
    desktop-file-utils \
    fakeroot \
    file \
    gdk-pixbuf2.0-bin \
    gnupg2 \
    libglib2.0-bin \
    libfuse2 \
    libgtk-3-bin \
    patchelf \
    python3 \
    python3-pip \
    shared-mime-info \
    squashfs-tools \
    xz-utils \
    zsync \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir appimage-builder==1.1.0 "packaging<22"

WORKDIR /workspace
