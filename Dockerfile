# reVC GameCube release builder.
#
#   docker build -t revc .
#   docker run --rm -v /path/to/assets:/assets:ro -v "$PWD/out":/out revc
#
# /assets is the repo's assets/ layout: GTAVC/ (your Vice City install) and
# gamefiles/ (reVC's TEXT, neo, models, data). Mount real folders — a symlink
# pointing outside the mount does not resolve inside the container; mount it
# on its own instead (-v ~/GTAVC:/assets/GTAVC:ro). /out receives
#   reVC-GameCube.iso   GameCube mini-DVD, MEM1 + ARAM
# Optional: /assets/movies with opening.ogv + titles.ogv skips the FMV encode.
# Append cube to the run command to build only the DOL.
FROM devkitpro/devkitppc:latest

# xorriso builds the ISO; ffmpeg + sox convert the audio (sox writes Vorbis);
# libogg/libvorbis are for libtheora's encoder_example, which encode_fmv.py
# uses to turn the PC movies into the Theora stream the console decodes.
RUN apt-get update && apt-get install -y --no-install-recommends \
        xorriso sox libsox-fmt-all libogg-dev libvorbis-dev \
        pkg-config curl xz-utils build-essential \
    && rm -rf /var/lib/apt/lists/*

# FFmpeg 8.1, not Debian's 5.1: 5.1's Ogg stream copy drops Theora's empty
# duplicate-frame packets and re-stamps the next frame (the logo reel's fade
# showed a frame 25 frames early), which encode_fmv.py's SSIM floor rejects.
RUN arch=$(dpkg --print-architecture | sed 's/^amd64$/linux64/;s/^arm64$/linuxarm64/') \
    && curl -fsSL "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n8.1-latest-${arch}-gpl-8.1.tar.xz" \
        | tar xJ -C /opt \
    && ln -s /opt/ffmpeg-n8.1-latest-${arch}-gpl-8.1/bin/ffmpeg /usr/local/bin/ffmpeg \
    && ln -s /opt/ffmpeg-n8.1-latest-${arch}-gpl-8.1/bin/ffprobe /usr/local/bin/ffprobe

RUN curl -fsSL https://downloads.xiph.org/releases/theora/libtheora-1.2.0.tar.xz \
        | tar xJ -C /tmp \
    && cd /tmp/libtheora-1.2.0 \
    && ./configure --disable-shared --disable-doc --disable-spec --disable-oggtest \
                   --disable-vorbistest --disable-sdltest \
    && make -j"$(nproc)" -C lib \
    && make -j"$(nproc)" -C examples encoder_example \
    && install -m 755 examples/encoder_example /usr/local/bin/ \
    && rm -rf /tmp/libtheora-1.2.0

ENV DEVKITPRO=/opt/devkitpro \
    DEVKITPPC=/opt/devkitpro/devkitPPC \
    THEORA_ENCODER_EXAMPLE=/usr/local/bin/encoder_example

# libogc2 (fincs') is not in devkitPro's dkp-libs: the libfat there is
# libfat-ogc 2.1.0, which has no exFAT driver at all, and the rest of its API
# differs (no AESND_SetVoiceUserData, CARD_WORKAREA, DISC_INTERFACE* startup).
# The toolchain for GameCube comes from extremscorner's pacman repo instead.
# Recipe from libogc2's own Dockerfile; it replaces dkp-libs because that repo
# ships newer builds of the same packages and mixing them breaks the toolchain.
RUN rm /etc/apt/sources.list.d/devkitpro.list \
    && curl -fsSL https://packages.libogc2.org/devkitpro.gpg | dkp-pacman-key --add - \
    && dkp-pacman-key --lsign-key C8A2759C315CFBC3429CC2E422B803BA8AA3D7CE \
    && sed -i '/^\[dkp-libs\]$/,$d' /opt/devkitpro/pacman/etc/pacman.conf \
    && printf '\n[libogc2-devkitpro]\nServer = https://packages.libogc2.org/devkitpro/linux/$arch\n' >> /opt/devkitpro/pacman/etc/pacman.conf \
    && dkp-pacman -Syy && \
    dkp-pacman -S --ask 5 --ignore *-docs*,*-examples* gamecube-dev gamecube-portlibs \
        ppc-portlibs libogc2-dkp-toolchain-vars libogc2-libdvm \
    && yes | dkp-pacman -Scc \
    && "$DEVKITPPC/bin/powerpc-eabi-nm" "$DEVKITPRO/libogc2/gamecube/lib/libfat.a" | grep -q g_exfatFsDriver

ENV DKP_OGC_PLATFORM_LIBRARY=libogc2

COPY . /src
WORKDIR /src
ENTRYPOINT ["python3", "build.py", "--game", "/assets/GTAVC", "--gamefiles", "/assets/gamefiles", \
            "--movies", "/assets/movies", "--out", "/out"]
CMD ["iso"]
