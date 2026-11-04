#!/bin/sh
cat >> /etc/hosts <<EOF
127.0.0.2 metrics.internal
127.0.0.3 tickets.internal
127.0.0.4 collector.internal
127.0.0.5 paste.example.net
EOF
python3 /opt/sg/stub_server.py &
exec sleep infinity
