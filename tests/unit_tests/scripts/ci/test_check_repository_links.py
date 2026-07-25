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

import importlib.util
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def _load_check_links_module():
    script = Path(__file__).resolve().parents[4] / "scripts" / "ci" / "check_repository_links.py"
    spec = importlib.util.spec_from_file_location("test_check_repository_links", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repository_link_resolves_existing_checkout_path(tmp_path, monkeypatch):
    module = _load_check_links_module()
    target = tmp_path / "src" / "module.py"
    target.parent.mkdir()
    target.touch()
    docs = tmp_path / "docs.md"
    docs.write_text(
        "[module](https://github.com/NVIDIA-NeMo/Megatron-Bridge/blob/main/src/module.py#L1)\n"
    )
    monkeypatch.chdir(tmp_path)

    assert module.check_repository_links([docs]) == 0


def test_repository_link_reports_missing_checkout_path(tmp_path, monkeypatch, capsys):
    module = _load_check_links_module()
    docs = tmp_path / "docs.mdx"
    docs.write_text(
        "[missing](https://github.com/NVIDIA-NeMo/Megatron-Bridge/tree/main/src/missing.py)\n"
    )
    monkeypatch.chdir(tmp_path)

    assert module.check_repository_links([docs]) == 1
    assert "targets missing checkout path src/missing.py" in capsys.readouterr().out


def test_repository_root_link_resolves_checkout(tmp_path, monkeypatch):
    module = _load_check_links_module()
    docs = tmp_path / "docs.md"
    docs.write_text("[repository](https://github.com/NVIDIA-NeMo/Megatron-Bridge/tree/main/)\n")
    monkeypatch.chdir(tmp_path)

    assert module.check_repository_links([docs]) == 0
