# Official Palworld v1.0.5.102999. Only the game payload enters the Wolfi image.
FROM ghcr.io/pocketpairjp/palserver:v1.0.5.102999@sha256:78d5edea9214c5c76628ea3ad29935052f837489f7f73ffa37654da14ee37892 AS upstream
USER 0
RUN rm -f /pal/Package/Pal/Binaries/Linux/*.debug /pal/Package/Pal/Binaries/Linux/*.sym
FROM squab-palworld:verify-amd64
USER 0
COPY --from=upstream /pal/Package /opt/palworld
RUN rm -rf /opt/palworld/Pal/Saved && ln -s /data /opt/palworld/Pal/Saved && \
    ln -sf /opt/palworld/linux64/steamclient.so /opt/palworld/Pal/Binaries/Linux/steamclient.so && \
    chmod 0555 /opt/palworld/Pal/Binaries/Linux/PalServer-Linux-Shipping
USER 65532:65532
HEALTHCHECK --interval=5s --timeout=4s --start-period=300s --retries=3 CMD ["/usr/local/bin/squab-palworld-launcher", "--healthcheck"]
