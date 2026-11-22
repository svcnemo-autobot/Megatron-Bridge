"""Remove paths that the builder's base flattening resurrected (validation-only; never in a PR).

The OCI builder flattens the deep validation image before extending it. Its flattened layer
restores paths that later base layers had deleted, such as the clone-era
3rdparty/Megatron-LM/.git with root-owned 0600 promisor packs and system packages removed by
`pip uninstall`. This script deletes only such paths:

* Under each recorded root, any path absent from the inventory recorded from the unflattened
  base image (skipping subtrees that inventory could not read or that were mounts).
* Inside the /opt/Megatron-Bridge subtrees that inventory could not read, any non-symlink path
  not owned by uid 1000, because the base's last layer that touches that tree runs
  `chown -R 1000:1000 /opt/Megatron-Bridge` (which leaves symlinks themselves unchanged).
"""

import collections
import gzip
import json
import os
import shutil
import sys

BRIDGE = "/opt/Megatron-Bridge"


def main(inventory, dry_run):
    with gzip.open(inventory) as fh:
        doc = json.load(fh)
    base = set(doc["entries"])
    skip = set(doc["skip"])
    removed = []

    def drop(path):
        removed.append(path)
        if dry_run:
            return
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.unlink(path)

    def walk(root, is_extra):
        for dirpath, dirnames, filenames in os.walk(root, onerror=None if not dry_run else (lambda e: None)):
            keep = []
            for name in dirnames:
                path = os.path.join(dirpath, name)
                if path in skip:
                    continue
                if is_extra(path):
                    drop(path)
                    continue
                if not os.path.islink(path):
                    keep.append(name)
            dirnames[:] = keep
            for name in filenames:
                path = os.path.join(dirpath, name)
                if path not in skip and is_extra(path):
                    drop(path)

    for root in doc["roots"]:
        walk(root, lambda path: path not in base)
    for unread in sorted(skip):
        if unread.startswith(BRIDGE + "/") and os.path.isdir(unread) and not os.path.islink(unread):
            walk(unread, lambda path: not os.path.islink(path) and os.lstat(path).st_uid != 1000)

    groups = collections.Counter("/".join(p.split("/")[:5]) for p in removed)
    print(f"restore_base_paths: {'would remove' if dry_run else 'removed'} {len(removed)} paths")
    for prefix, count in sorted(groups.items()):
        print(f"  {count:7d} {prefix}")
    for path in removed[:100]:
        print(f"  path {path}")


if __name__ == "__main__":
    main(sys.argv[1], "--dry-run" in sys.argv[2:])
