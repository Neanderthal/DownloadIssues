"""Centralized configuration for the data transfer pipeline."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Provider selection: "github" or "gitflic"
PROVIDER = os.environ.get("PROVIDER", "gitflic")

# GitHub
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_API_URL = "https://api.github.com"
GRAPHQL_API_URL = "https://api.github.com/graphql"

# GitFlic
GITFLIC_TOKEN = os.environ.get("GITFLIC_TOKEN", "")
GITFLIC_PROJECT = os.environ.get("GITFLIC_PROJECT", "")  # owner/project
GITFLIC_API_URL = "https://api.gitflic.ru"

# GPG
GPG_KEY = os.environ.get("GPG_KEY", "neanderthal")

# Paths
OUTPUT_DIR = Path(os.environ.get("ISSUES_DIR", "data/projects/issues"))
EXTRACTED_DIR = Path("extracted")

# Data transfer constants
HEX_CHARS_PER_CHUNK = 62464
TRANSFER_LABEL = "data-transfer"
TITLE_PREFIX = "[DT]"


def get_repo_for_provider(provider: str, override: str | None = None) -> str:
    """Return the repo/project string for the active provider."""
    if override:
        return override
    if provider == "gitflic":
        return GITFLIC_PROJECT
    return GITHUB_REPO
