# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Validate repository-local GitHub links against the current checkout."""

import re
from pathlib import Path
from urllib.parse import unquote, urlparse


_REPOSITORY_URL_PATTERN = re.compile(
    r"https://github\.com/NVIDIA-NeMo/Megatron-Bridge/(?:blob|tree)/main(?:/[^\s)>\"']*)?"
)
_REPOSITORY_PATH_PATTERN = re.compile(
    r"^/NVIDIA-NeMo/Megatron-Bridge/(?:blob|tree)/main(?:/(?P<path>.*))?$"
)


def _repository_path(url: str) -> Path | None:
    """Return the checkout path targeted by a repository-local GitHub URL."""
    match = _REPOSITORY_PATH_PATTERN.fullmatch(urlparse(url).path)
    if match is None:
        return None
    return Path(unquote(match.group("path") or "."))


def _repository_links(paths: list[Path]) -> list[tuple[Path, str]]:
    """Collect repository-local GitHub targets from Markdown and MDX files."""
    links: list[tuple[Path, str]] = []
    for path in paths:
        for url in _REPOSITORY_URL_PATTERN.findall(path.read_text()):
            links.append((path, url.rstrip(".,")))
    return links


def check_repository_links(paths: list[Path]) -> int:
    """Report repository-local GitHub links whose checked-out targets do not exist."""
    failures = []
    for source, url in _repository_links(paths):
        target = _repository_path(url)
        if target is not None and not target.exists():
            failures.append((source, url, target))

    for source, url, target in failures:
        print(f"{source}: {url} targets missing checkout path {target}")
    return 1 if failures else 0


def main() -> int:
    """Validate every Markdown and MDX file under the documentation tree."""
    paths = [path for path in Path("docs").rglob("*") if path.suffix in {".md", ".mdx"}]
    return check_repository_links(paths)


if __name__ == "__main__":
    raise SystemExit(main())
