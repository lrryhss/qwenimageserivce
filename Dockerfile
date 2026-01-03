# Qwen-Image-2512 API Server for Jetson Thor
FROM ghcr.io/nvidia-ai-iot/vllm:latest-jetson-thor

WORKDIR /app

# Install Qwen-Image dependencies
RUN pip3 install --no-cache-dir \
    "pillow" \
    "accelerate" \
    "fastapi" \
    "uvicorn[standard]" \
    "python-multipart"

# Upgrade diffusers and transformers (base image has older pinned versions)
# Clear pip constraints and force install latest
RUN PIP_CONSTRAINT="" pip3 install --no-cache-dir --upgrade \
    transformers \
    git+https://github.com/huggingface/diffusers

# Copy server code and frontend
COPY server.py .
COPY frontend/ frontend/

# Environment
ENV PORT=8002
ENV DEVICE=cuda
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/models

# Model cache volume
VOLUME /models

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=30s --start-period=10m --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["python3", "server.py"]
