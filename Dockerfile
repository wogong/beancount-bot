FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ADD . /app
WORKDIR /app
RUN uv sync --frozen

#CMD python3 /codebase/beanbot.py;
ENTRYPOINT ["uv", "run","src/bot.py"]
