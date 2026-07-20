# Minimal hello_world image for sandbox toolchain validation.
FROM python:3.12-slim
RUN python -c "print('hello_world build stage ok')"
WORKDIR /work
CMD ["python", "-c", "import sys, platform; print('hello_world from', platform.python_version()); print('argv', sys.argv)"]
