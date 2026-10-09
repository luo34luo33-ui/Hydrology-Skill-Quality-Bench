# Build only with explicit digest/version arguments. Never use latest for formal runs.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG CODEX_VERSION
ARG OPENCODE_VERSION
ARG QWEN_VERSION
ARG CODEBUDDY_VERSION
ARG NODE_VERSION
USER root
COPY runtime/requirements.lock.txt /opt/requirements.lock.txt
RUN micromamba create -y -n HydroTune-eval python=3.11 nodejs=${NODE_VERSION} ripgrep=15.1.0 -c conda-forge && micromamba clean --all --yes
ENV PATH=/opt/conda/envs/HydroTune-eval/bin:$PATH
RUN test -x /opt/conda/envs/HydroTune-eval/bin/rg && rg --version | grep -q '^ripgrep 15.1.0'
RUN python -m pip install --no-cache-dir -r /opt/requirements.lock.txt && test -n "$CODEX_VERSION" && test -n "$OPENCODE_VERSION" && test -n "$QWEN_VERSION" && npm install -g @openai/codex@${CODEX_VERSION} opencode-ai@${OPENCODE_VERSION} @qwen-code/qwen-code@${QWEN_VERSION}
RUN if [ -n "$CODEBUDDY_VERSION" ]; then npm install -g @tencent-ai/codebuddy-code@${CODEBUDDY_VERSION}; fi
# Linux WhiteboxTools is supplied as a separately verified build artifact.
COPY runtime/vendor/linux/ /opt/whitebox/
RUN chmod +x /opt/whitebox/whitebox_tools && /opt/whitebox/whitebox_tools --version
COPY runtime/entrypoint.py /opt/entrypoint.py
COPY runtime/atomic_entrypoint.py /opt/atomic_entrypoint.py
COPY harness/cli_events.py /opt/cli_events.py
RUN chmod +x /opt/entrypoint.py && useradd -m -u 10001 agent && ln -s /opt/conda/envs/HydroTune-eval/bin/python /usr/local/bin/python && ln -s /opt/conda/envs/HydroTune-eval/bin/python /usr/local/bin/python3
ENV HOME=/home/agent WBT_PATH=/opt/whitebox HSQB_WHITEBOX_DIR=/opt/whitebox
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
USER agent
WORKDIR /work
