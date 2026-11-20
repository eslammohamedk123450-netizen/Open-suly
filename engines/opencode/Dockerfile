# Build context: SULY repository root, with engines/opencode/upstream initialized.
# The upstream revision is verified separately by verify_upstream.py.
FROM oven/bun:1.4.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates python3 make g++ \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 opencode \
    && useradd --system --uid 10001 --gid opencode --create-home --home-dir /home/opencode opencode

WORKDIR /opt/opencode
COPY engines/opencode/upstream/ ./

# Install only from the upstream lockfile; never resolve floating dependencies at runtime.
RUN bun install --frozen-lockfile \
    && mkdir -p /workspace /var/lib/opencode/config /var/lib/opencode/data \
    && chown -R opencode:opencode /workspace /var/lib/opencode /home/opencode

ENV NODE_ENV=production \
    OPENCODE_CONFIG_DIR=/var/lib/opencode/config \
    HOME=/home/opencode \
    NO_PROXY=127.0.0.1,localhost,::1 \
    no_proxy=127.0.0.1,localhost,::1

WORKDIR /workspace
USER 10001:10001

# EXPOSE is documentation only; do not publish this port to the host.
EXPOSE 4096

CMD ["bun", "run", "--cwd", "/opt/opencode/packages/cli", "src/index.ts", "serve", "--hostname", "0.0.0.0", "--port", "4096"]
