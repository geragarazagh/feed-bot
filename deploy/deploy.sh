#!/bin/sh
# Ship the current commit to the server and (re)install it. Runs on the admin's computer.
#   VM=tgfeed ZONE=us-east1-b sh deploy/deploy.sh
# SSH goes through Identity-Aware Proxy, so the server needs no public IPv4 address.
set -eu
VM=${VM:-tgfeed}
ZONE=${ZONE:-us-east1-b}
cd "$(dirname "$0")/.."
TAR=$(mktemp -t feedbot.XXXXXX)
git archive --format=tar.gz -o "$TAR" HEAD
timeout 300 gcloud compute scp --zone "$ZONE" --tunnel-through-iap --quiet "$TAR" "$VM:/tmp/feedbot.tar.gz"
rm -f "$TAR"
timeout 600 gcloud compute ssh "$VM" --zone "$ZONE" --tunnel-through-iap --quiet --command \
  'set -e; rm -rf /tmp/feedbot-src; mkdir /tmp/feedbot-src; tar -xzf /tmp/feedbot.tar.gz -C /tmp/feedbot-src; sudo sh /tmp/feedbot-src/deploy/install.sh; rm -rf /tmp/feedbot-src /tmp/feedbot.tar.gz'
