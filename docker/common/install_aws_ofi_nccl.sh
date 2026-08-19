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

#!/bin/bash

# Build and install the aws-ofi-nccl NCCL network plugin (the NCCL <-> libfabric
# bridge that lets NCCL run over AWS EFA).
#
# Why this exists: the NVIDIA PyTorch >= 26.06 base image dropped aws-ofi-nccl
# and now defaults NCCL_NET_PLUGIN=spcx (HPCX Spectrum-X). On an EFA fabric the
# Spectrum-X plugin cannot drive the NICs, so NCCL cannot use EFA. The
# EFA/libfabric userspace is still in the image (/opt/amazon/efa) and the base even
# keeps a dangling /etc/ld.so.conf.d/aws-ofi-nccl.conf -> /opt/amazon/ofi-nccl/lib,
# so we only need to rebuild the plugin and drop it back into that same prefix.

set -euo pipefail

AWS_OFI_NCCL_COMMIT="13383fa86cd5a13e57b2835390ba089a384e398c"

for i in "$@"; do
    case $i in
        --AWS_OFI_NCCL_COMMIT=?*) AWS_OFI_NCCL_COMMIT="${i#*=}";;
        *) ;;
    esac
    shift
done

PREFIX="/opt/amazon/ofi-nccl"
SRC_DIR="$(mktemp -d)"

apt-get update
apt-get install -y --no-install-recommends \
    git ca-certificates build-essential autoconf automake libtool libhwloc-dev
apt-get clean
rm -rf /var/lib/apt/lists/*

git clone --filter=blob:none --no-checkout \
    https://github.com/aws/aws-ofi-nccl.git "${SRC_DIR}"
git -C "${SRC_DIR}" fetch --depth 1 origin "${AWS_OFI_NCCL_COMMIT}"
git -C "${SRC_DIR}" checkout --detach FETCH_HEAD
test "$(git -C "${SRC_DIR}" rev-parse HEAD)" = "${AWS_OFI_NCCL_COMMIT}"

pushd "${SRC_DIR}"
./autogen.sh
# libfabric ships under /opt/amazon/efa; NCCL headers/lib come from libnccl-dev in
# the system prefix (/usr). --enable-platform-aws pulls in the EFA tunings.
./configure \
    --prefix="${PREFIX}" \
    --with-libfabric=/opt/amazon/efa \
    --with-cuda=/usr/local/cuda \
    --with-nccl=/usr \
    --enable-platform-aws \
    --disable-tests
make -j"$(nproc)"
make install
popd

# Revive the ldconfig entry the base image left behind so a bare `libnccl-net.so`
# lookup can also resolve here; EKSEnvPlugin still pins the absolute path.
echo "${PREFIX}/lib" > /etc/ld.so.conf.d/aws-ofi-nccl.conf
ldconfig

rm -rf "${SRC_DIR}"
