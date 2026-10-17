#!/bin/bash
# Queue hygiene and sprint view tests; see test_queue.py. Pass a QUEUE.md path to also test a copy of it.
exec python3 "$(cd "$(dirname "$0")" && pwd)/test_queue.py" "$@"
