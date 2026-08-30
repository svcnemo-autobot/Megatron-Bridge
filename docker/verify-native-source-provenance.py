# Copyright (c) 2026, NVIDIA CORPORATION. All rights reserved.
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

"""Verify native package sources selected by frozen Megatron Core and Bridge manifests."""

import argparse
import json
import re
from pathlib import Path
from typing import Any

import tomllib
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name


_GIT_OID_PART = re.compile(r"[0-9a-f]{20}")


def _require(condition: bool, message: str) -> None:
    """Reject invalid provenance without relying on optimizable assertions."""
    if not condition:
        raise ValueError(message)


def _git_commit(value: dict[str, Any], label: str) -> str:
    """Reconstruct and validate a split Git object ID."""
    _require(
        value.get("object_format") == "40-hex-git-oid",
        f"invalid object format for {label}",
    )
    parts = value.get("parts")
    _require(isinstance(parts, list) and len(parts) == 2, f"invalid parts for {label}")
    _require(
        all(isinstance(part, str) and _GIT_OID_PART.fullmatch(part) for part in parts),
        f"invalid Git object ID for {label}",
    )
    return "".join(parts)


def _lane(manifest: dict[str, Any], mcore_ref: str) -> dict[str, Any]:
    """Return the unique lane selected by an immutable MCore commit."""
    lanes = [
        lane for lane in manifest["lanes"] if _git_commit(lane["mcore_commit"], f"{lane['name']} MCore") == mcore_ref
    ]
    _require(len(lanes) == 1, f"unknown or duplicate MCore provenance: {mcore_ref}")
    return lanes[0]


def _source(lane: dict[str, Any], name: str) -> dict[str, Any]:
    """Return one required native source record."""
    source = lane["native_sources"].get(name)
    _require(isinstance(source, dict), f"missing {name} source provenance")
    _require(
        isinstance(source.get("repository"), str) and source["repository"].startswith("https://github.com/"),
        f"invalid {name} repository",
    )
    _require(isinstance(source.get("package"), str), f"invalid {name} package")
    return source


def _build_commit(lane: dict[str, Any], name: str) -> str:
    """Return one native source commit used by the build cache."""
    return _git_commit(_source(lane, name)["build_commit"], f"{name} build")


def _uv_sources(path: Path) -> dict[str, Any]:
    """Parse and canonicalize effective uv source declarations."""
    with path.open("rb") as manifest_file:
        manifest = tomllib.load(manifest_file)
    raw_sources = manifest.get("tool", {}).get("uv", {}).get("sources", {})
    _require(isinstance(raw_sources, dict), "invalid tool.uv.sources table")
    sources: dict[str, Any] = {}
    for package, declaration in raw_sources.items():
        canonical_package = canonicalize_name(package)
        _require(canonical_package not in sources, f"duplicate canonical source for {canonical_package}")
        sources[canonical_package] = declaration
    return sources


def _source_entries(sources: dict[str, Any], package: str) -> list[dict[str, Any]]:
    """Return normalized source entries for one package."""
    entries = sources.get(canonicalize_name(package), [])
    if isinstance(entries, dict):
        entries = [entries]
    _require(
        isinstance(entries, list) and all(isinstance(entry, dict) for entry in entries),
        f"invalid {package} source declaration",
    )
    return entries


def _inventory_revision(record: dict[str, Any], label: str) -> str:
    """Read a literal tag/branch or reconstruct an immutable revision."""
    if "revision_value" in record:
        revision = record["revision_value"]
        _require(isinstance(revision, str) and revision, f"invalid revision for {label}")
        return revision
    return _git_commit(record["revision"], label)


def _verify_inventory(sources: dict[str, Any], inventory: dict[str, Any], label: str) -> None:
    """Require the complete Git source table to match the reviewed inventory."""
    _require(isinstance(inventory, dict), f"invalid {label} Git source inventory")
    expected: dict[str, Any] = {}
    for package, record in inventory.items():
        canonical_package = canonicalize_name(package)
        _require(canonical_package == package, f"non-canonical {label} inventory package: {package}")
        _require(canonical_package not in expected, f"duplicate {label} inventory package: {package}")
        expected[canonical_package] = record
    _require(set(sources) == set(expected), f"{label} source inventory does not match provenance")
    for package, record in expected.items():
        _require(isinstance(record, dict), f"invalid {label} inventory entry for {package}")
        raw_declaration = sources[package]
        shape = "list" if isinstance(raw_declaration, list) else "table"
        _require(shape == record.get("entry_shape"), f"{label} source shape changed for {package}")
        entries = _source_entries(sources, package)
        _require(len(entries) == 1, f"{label} must have exactly one source for {package}")
        entry = entries[0]
        _require(set(entry) == {"git", "rev"}, f"{label} source must be unconditional for {package}")
        _require(
            entry["git"] == record.get("repository")
            and entry["rev"] == _inventory_revision(record, f"{label} {package}"),
            f"{label} source does not match provenance for {package}",
        )


def _verify_exact_source(sources: dict[str, Any], package: str, repository: str, revision: str, label: str) -> None:
    """Require exactly one unconditional source at the approved repository and revision."""
    entries = _source_entries(sources, package)
    _require(len(entries) == 1, f"{label} must have exactly one source declaration")
    entry = entries[0]
    _require(set(entry) == {"git", "rev"}, f"{label} source must be unconditional")
    _require(
        entry["git"] == repository and entry["rev"] == revision,
        f"{label} source does not match provenance",
    )


def _verify_mcore_manifest(lane: dict[str, Any], path: Path) -> None:
    """Verify the complete Git inventory and active native sources in frozen MCore metadata."""
    sources = _uv_sources(path)
    _verify_inventory(sources, lane["mcore_source_inventory"], "MCore")
    for name, source in lane["native_sources"].items():
        package = name.replace("_", "-")
        entries = _source_entries(sources, package)
        if source is None:
            _require(not entries, f"unexpected {package} source in MCore manifest")
            continue
        _verify_exact_source(
            sources,
            source["package"],
            source["repository"],
            _git_commit(source["mcore_commit"], f"{name} MCore"),
            f"{source['package']} MCore",
        )


def _requirement(value: str, label: str) -> Requirement:
    """Parse one PEP 508 requirement with a stable validation error."""
    try:
        return Requirement(value)
    except InvalidRequirement as error:
        raise ValueError(f"invalid {label} dependency") from error


def _all_requirements(manifest: dict[str, Any]) -> list[Requirement]:
    """Collect requirements that can select direct VCS sources during a Bridge sync."""
    requirement_values: list[str] = []
    project = manifest.get("project", {})
    requirement_values.extend(project.get("dependencies", []))
    for values in project.get("optional-dependencies", {}).values():
        requirement_values.extend(values)
    for values in manifest.get("dependency-groups", {}).values():
        requirement_values.extend(value for value in values if isinstance(value, str))
    requirement_values.extend(manifest.get("build-system", {}).get("requires", []))
    requirement_values.extend(manifest.get("tool", {}).get("uv", {}).get("override-dependencies", []))
    _require(all(isinstance(value, str) for value in requirement_values), "invalid Bridge dependency list")
    return [_requirement(value, "Bridge") for value in requirement_values]


def _verify_bridge_manifest(lane: dict[str, Any], path: Path) -> None:
    """Verify Bridge selectors and enforce explicit absence of MCore-owned sources."""
    with path.open("rb") as manifest_file:
        manifest = tomllib.load(manifest_file)
    sources = _uv_sources(path)
    overrides = manifest.get("tool", {}).get("uv", {}).get("override-dependencies", [])
    _require(isinstance(overrides, list), "invalid Bridge override dependencies")
    override_requirements = [_requirement(override, "Bridge override") for override in overrides]
    all_requirements = _all_requirements(manifest)
    for name, source in lane["native_sources"].items():
        package = source["package"] if source is not None else name.replace("_", "-")
        matching_urls = [
            requirement
            for requirement in all_requirements
            if canonicalize_name(requirement.name) == canonicalize_name(package) and requirement.url is not None
        ]
        if source is None:
            _require(not _source_entries(sources, package), f"unexpected {package} Bridge source")
            _require(not matching_urls, f"unexpected direct {package} Bridge requirement")
            continue
        selector = source["bridge_selector"]
        repository = source["repository"]
        if selector is None:
            _require(not _source_entries(sources, package), f"unexpected {package} Bridge source")
            _require(not matching_urls, f"unexpected direct {package} Bridge requirement")
            continue
        if selector["kind"] == "uv-source":
            revision = _git_commit(selector["commit"], f"{name} Bridge selector")
            _verify_exact_source(sources, package, repository, revision, f"{package} Bridge")
        elif selector["kind"] == "vcs-requirement":
            revision = selector.get("value")
            if revision is None:
                revision = _git_commit(selector["commit"], f"{name} Bridge selector")
            matching = [
                requirement
                for requirement in override_requirements
                if canonicalize_name(requirement.name) == canonicalize_name(package)
            ]
            _require(len(matching) == 1, f"{package} must have exactly one Bridge override")
            requirement = matching[0]
            _require(requirement.marker is None, f"{package} Bridge override must be unconditional")
            _require(
                requirement.url == f"git+{repository}@{revision}",
                f"{package} source does not match Bridge provenance",
            )
        else:
            raise ValueError(f"invalid {name} Bridge selector kind")


def _verify_lane_audit(manifest: dict[str, Any], lane: dict[str, Any]) -> None:
    """Bind the reviewed source transitions and native build entrypoints."""
    if lane["name"] != "main":
        return
    transformer_engine = _source(lane, "transformer_engine")
    transition = transformer_engine.get("transition", {})
    baseline = manifest["authority"]["baseline_bridge_transformer_engine"]
    _require(
        _git_commit(transition["prior_bridge_commit"], "prior Bridge TransformerEngine")
        == _git_commit(baseline["commit"], "baseline Bridge TransformerEngine"),
        "TransformerEngine transition baseline does not match provenance",
    )
    _require(
        _git_commit(transition["selected_mcore_commit"], "selected MCore TransformerEngine")
        == _git_commit(transformer_engine["mcore_commit"], "main TransformerEngine MCore"),
        "TransformerEngine transition target does not match MCore",
    )
    _require(transition.get("authority") == "frozen-mcore-manifest", "invalid TransformerEngine transition authority")
    _require(transition.get("disposition") == "bridge-selector-removed", "invalid TransformerEngine transition")
    torch_memory_saver = _source(lane, "torch_memory_saver")
    audit = torch_memory_saver.get("audit", {})
    _git_commit(audit["setup_py"], "torch-memory-saver setup.py")
    _git_commit(audit["manifest_in"], "torch-memory-saver MANIFEST.in")
    _require(audit.get("gitlinks") == "absent", "invalid torch-memory-saver gitlink policy")
    _require(audit.get("nested_fetches") == "absent", "invalid torch-memory-saver nested-fetch policy")


def main() -> None:
    """Validate lane provenance and the supplied source manifests."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--mcore-ref", required=True)
    parser.add_argument("--transformer-engine-ref")
    parser.add_argument("--fast-hadamard-transform-ref")
    parser.add_argument("--torch-memory-saver-ref")
    parser.add_argument("--torch-memory-saver-setup-ref")
    parser.add_argument("--torch-memory-saver-manifest-ref")
    parser.add_argument("--mcore-pyproject", type=Path)
    parser.add_argument("--bridge-pyproject", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    lane = _lane(manifest, args.mcore_ref)
    _verify_lane_audit(manifest, lane)
    if args.transformer_engine_ref is not None:
        _require(
            _build_commit(lane, "transformer_engine") == args.transformer_engine_ref,
            "TransformerEngine build source does not match provenance",
        )
    if args.fast_hadamard_transform_ref is not None:
        _require(
            _build_commit(lane, "fast_hadamard_transform") == args.fast_hadamard_transform_ref,
            "fast-hadamard-transform build source does not match provenance",
        )
    tms_audit_args = (args.torch_memory_saver_setup_ref, args.torch_memory_saver_manifest_ref)
    if args.torch_memory_saver_ref is not None or any(value is not None for value in tms_audit_args):
        _require(
            args.torch_memory_saver_ref is not None and all(tms_audit_args), "incomplete torch-memory-saver audit"
        )
        torch_memory_saver = _source(manifest["lanes"][0], "torch_memory_saver")
        _require(
            _git_commit(torch_memory_saver["build_commit"], "torch-memory-saver build") == args.torch_memory_saver_ref,
            "torch-memory-saver build source does not match provenance",
        )
        _require(
            _git_commit(torch_memory_saver["audit"]["setup_py"], "torch-memory-saver setup.py")
            == args.torch_memory_saver_setup_ref,
            "torch-memory-saver setup.py does not match provenance",
        )
        _require(
            _git_commit(torch_memory_saver["audit"]["manifest_in"], "torch-memory-saver MANIFEST.in")
            == args.torch_memory_saver_manifest_ref,
            "torch-memory-saver MANIFEST.in does not match provenance",
        )
    if args.mcore_pyproject is not None:
        _verify_mcore_manifest(lane, args.mcore_pyproject)
    if args.bridge_pyproject is not None:
        _verify_bridge_manifest(lane, args.bridge_pyproject)


if __name__ == "__main__":
    main()
