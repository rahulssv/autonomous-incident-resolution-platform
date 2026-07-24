FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The Bob CLI ships as the npm package 'bobshell'; its entrypoint is a Node
# bundle (bundle/bob.js) with a '#!/usr/bin/env node' shebang. Node is copied
# from the official image built on the same Debian release as python:3.12-slim
# (trixie), so the binary is ABI-compatible.
COPY --from=node:22-trixie-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-trixie-slim /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm

# bobshell is not published to the public npm registry. Either
#   (a) build with --build-arg BOB_NPM_REGISTRY=<internal registry>, or
#   (b) vendor the bundle into ./vendor/bobshell (run scripts/vendor-bob.sh).
# Both land on /usr/local/lib/node_modules/bobshell/bundle/bob.js. Without one
# of them the image has no CLI at all and every LLM call fails with
# "Cannot find module .../bundle/bob.js".
#
# vendor/ always exists (it holds a .gitkeep) so this COPY never breaks a build
# that uses option (a) or no Bob at all.
COPY vendor/ /tmp/vendor/
ARG BOB_NPM_REGISTRY=""
RUN if [ -n "$BOB_NPM_REGISTRY" ]; then \
        npm install -g --registry="$BOB_NPM_REGISTRY" bobshell; \
    elif [ -f /tmp/vendor/bobshell/bundle/bob.js ]; then \
        mkdir -p /usr/local/lib/node_modules && \
        cp -r /tmp/vendor/bobshell /usr/local/lib/node_modules/bobshell; \
    fi; \
    rm -rf /tmp/vendor

RUN addgroup --system airp && adduser --system --ingroup airp airp

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src

RUN pip install --upgrade pip && pip install .

# Run the bundle through node explicitly — a copied bundle has no exec bit,
# and bob_cli_client prefixes 'node' for any .js path.
ENV AIRP_BOB_CLI_PATH=/usr/local/lib/node_modules/bobshell/bundle/bob.js

USER airp

EXPOSE 8080

CMD ["uvicorn", "airp.main:app", "--host", "0.0.0.0", "--port", "8080"]
