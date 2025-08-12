# Stage 1: Retrieve the Terraform binary from the distroless image
FROM hashicorp/terraform:1.12 AS terraform

FROM python:3.13-alpine3.20 AS base

WORKDIR /home/fclicks

# run this only if you need to run docker commands from the container, then comment out the next line
# also comment the `USER fclicks` line for this to work with docker commands for now.
# RUN apk add --no-cache docker docker-cli-compose && \
#     adduser -D -h /home/fclicks fclicks && \
#     addgroup fclicks docker && \
#     chown -R fclicks:fclicks /home/fclicks

RUN addgroup -g 1001 fclicks && \
    adduser -u 1001 -S -G fclicks fclicks

RUN apk add --no-cache \
    openssh

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --from=terraform /bin/terraform /bin/terraform

USER fclicks

COPY uv.lock pyproject.toml ./
RUN uv sync --locked

COPY app app

EXPOSE 8000

VOLUME [ "/home/fclicks/app", "/home/fclicks/tasks" ]

FROM base AS dev

USER root

RUN apk add --no-cache aws-cli

USER fclicks

RUN uv pip install debugpy

EXPOSE 5678

CMD [ ".venv/bin/python", "-Xfrozen_modules=off", "-m", "debugpy", "--listen", "0.0.0.0:5678", "-m", "app.debug"]

FROM base AS prod
CMD ["uv", "run", "fastapi", "run", "--app", "app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

