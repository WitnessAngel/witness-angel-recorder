#!/bin/bash
source ~/.venv/bin/activate
# See https://github.com/python-poetry/poetry/issues/3662 for PYTHON_KEYRING_BACKEND
export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring
# Beware, keep that in sync with Kivy version of pyproject.toml, we must install it without multiprocessing else RAM explodes
##pip install --global-option="-j1" Kivy==2.0.0 - nope doesn't work
poetry install
poetry config installer.max-workers 1  # Protect RAM limits
