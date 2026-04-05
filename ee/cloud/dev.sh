#!/bin/bash
set -e

cd "$(dirname "$0")"
exec mprocs --config mprocs.yaml
