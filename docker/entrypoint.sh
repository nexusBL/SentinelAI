#!/bin/sh
set -e

mkdir -p /app/artifacts/runs /app/memory_store /app/auth_store
chown -R pwuser:pwuser /app/artifacts /app/memory_store /app/auth_store

exec runuser -u pwuser -- "$@"
