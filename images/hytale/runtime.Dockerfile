FROM squab-hytale:verify-amd64
HEALTHCHECK --interval=5s --timeout=4s --start-period=900s --retries=3 CMD ["/usr/local/bin/squab-hytale-setup", "--healthcheck"]
