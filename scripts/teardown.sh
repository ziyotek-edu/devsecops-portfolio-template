#!/usr/bin/env bash
# Tear down the local portfolio cluster
set -euo pipefail

CLUSTER_NAME="portfolio"

echo "Deleting kind cluster '${CLUSTER_NAME}'..."
kind delete cluster --name "$CLUSTER_NAME"
echo "✓ Cluster deleted"
