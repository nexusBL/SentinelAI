#!/bin/sh
set -e

mkdir -p /app/artifacts/runs /app/memory_store /app/metadata_store
chown -R pwuser:pwuser /app/artifacts /app/memory_store /app/metadata_store

exec runuser -u pwuser -- "$@"
