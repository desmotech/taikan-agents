FROM python:3.11-slim AS builder

ARG HERMES_GIT_REF=v2026.8.27

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN test -n "${HERMES_GIT_REF}" \
  && git init /opt/hermes-agent \
  && git -C /opt/hermes-agent remote add origin https://github.com/NousResearch/hermes-agent.git \
  && git -C /opt/hermes-agent fetch --depth 1 origin "${HERMES_GIT_REF}" \
  && git -C /opt/hermes-agent checkout --detach FETCH_HEAD \
  && test "$(git -C /opt/hermes-agent rev-parse HEAD)" = "5fc308a70719a83cccdbba4c0e39c23f5a8239d5" \
  && git -C /opt/hermes-agent submodule update --init --recursive --depth 1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir websockets -e "/opt/hermes-agent[slack,mcp,anthropic,cron,pty]"


FROM python:3.11-slim

ARG FASTLANE_VERSION=2.241.1

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    gh \
    nodejs \
    npm \
    ruby \
    tini \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends build-essential ruby-dev \
  && gem install fastlane -v "${FASTLANE_VERSION}" --no-document \
  && apt-get purge -y --auto-remove build-essential ruby-dev \
  && rm -rf /var/lib/apt/lists/*

# /data/.npm-global lets the unprivileged agent install npm CLIs on the volume.
# It is last on PATH so agent-written files never shadow the root supervisor's tools.
ENV PATH="/opt/venv/bin:${PATH}:/data/.npm-global/bin" \
  PYTHONUNBUFFERED=1 \
  HERMES_HOME=/data/.hermes \
  HOME=/data \
  NPM_CONFIG_PREFIX=/data/.npm-global

# The cost guard supervisor stays root (it holds the Anthropic key) and runs
# Hermes as this user, which cannot read root's /proc environment.
RUN useradd --system --uid 10001 --user-group --home-dir /data --no-create-home --shell /bin/bash hermes

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hermes-agent /opt/hermes-agent

WORKDIR /app
COPY scripts/entrypoint.sh scripts/release-client.py scripts/mobile-client.py scripts/cost_guard.py scripts/runtime_policy.py /app/scripts/
RUN chmod +x /app/scripts/entrypoint.sh /app/scripts/release-client.py /app/scripts/mobile-client.py
# taikan-agents: per-bot identity and config, selected at boot by $BOT
COPY souls /app/souls
COPY config /app/config
# mobile: store lanes, run from a scratch copy by scripts/mobile-client.py
COPY fastlane /app/fastlane

ENTRYPOINT ["tini", "--"]
CMD ["/app/scripts/entrypoint.sh"]
