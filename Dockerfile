FROM debian:12

WORKDIR /gtavc

# Instala dependencias necesarias para compilar
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y cmake ninja-build python3 wget apt-transport-https \
        build-essential autoconf automake libtool pkg-config git \
        libogg-dev libvorbis-dev ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Compila e instala encoder_example (Xiph libtheora) para el host: el encoding
# de FMV (.ogv) de build_sd.py lo requiere y Debian no lo empaqueta.
RUN git clone --depth 1 https://github.com/xiph/theora /tmp/theora && \
    cd /tmp/theora && \
    ./autogen.sh && \
    ./configure --disable-oggtest && \
    make -j"$(nproc)" && \
    make install && \
    install -m 755 examples/.libs/encoder_example /usr/local/bin/encoder_example && \
    ldconfig && \
    cd / && rm -rf /tmp/theora

# Descarga y ejecuta el script de instalación de devkitPro pacman
# (replica install-devkitpro-pacman con -y para un build no interactivo)
RUN mkdir -p /usr/share/keyring/ && \
    wget -U "dkp apt" -O /usr/share/keyring/devkitpro-pub.gpg https://apt.devkitpro.org/devkitpro-pub.gpg && \
    echo "deb [signed-by=/usr/share/keyring/devkitpro-pub.gpg] https://apt.devkitpro.org stable main" > /etc/apt/sources.list.d/devkitpro.list && \
    apt-get update && \
    apt-get install -y devkitpro-pacman && \
    rm -rf /var/lib/apt/lists/*

# Instala los paquetes de devkitPro (GameCube, Wii y portlibs ppc)
RUN ln -sf /proc/self/mounts /etc/mtab && \
    dkp-pacman -Syu --needed --noconfirm gamecube-dev wii-dev ppc-libogg ppc-libvorbisidec

ENV DEVKITPRO=/opt/devkitpro
ENV DEVKITPPC=$DEVKITPRO/devkitPPC
ENV PATH=$DEVKITPRO/tools/bin:$DEVKITPPC/bin:$PATH

# Compilación
COPY . .
RUN python3 build.py all