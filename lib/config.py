"""Centralized configuration for the data transfer pipeline."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# GitHub
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_API_URL = "https://api.github.com"
GRAPHQL_API_URL = "https://api.github.com/graphql"

# GPG
GPG_KEY = os.environ.get("GPG_KEY", "neanderthal")

# Paths
OUTPUT_DIR = Path(os.environ.get("ISSUES_DIR", "data/projects/issues"))
EXTRACTED_DIR = Path("extracted")

# Data transfer constants
HEX_CHARS_PER_CHUNK = 62464
TRANSFER_LABEL = "data-transfer"
TITLE_PREFIX = "[DT]"
