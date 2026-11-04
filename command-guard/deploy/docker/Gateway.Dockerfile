FROM ghcr.io/astral-sh/uv@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv
FROM docker@sha256:4d742ab934c2149b628bf26369ac3ec51cb91e2e28fe6722a0e86a6d6efc4bd5 AS docker
FROM python@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=docker /usr/local/bin/docker /usr/bin/docker
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable --python /usr/local/bin/python \
    && rm -rf /root/.cache/uv
ENV PATH=/app/.venv/bin:/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp
ENTRYPOINT ["python", "-m", "command_guard.container"]
