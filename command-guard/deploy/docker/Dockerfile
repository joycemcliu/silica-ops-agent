FROM python@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl dnsutils git jq openssh-client postgresql-client \
    procps ripgrep netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/usr/local/bin:/usr/bin:/bin
