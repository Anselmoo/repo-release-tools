FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY LICENSE README.md pyproject.toml ./
COPY .github/skills ./.github/skills
COPY .github/agents ./.github/agents
COPY .github/hooks ./.github/hooks
COPY src ./src

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

ENTRYPOINT ["rrt"]
CMD ["--help"]
