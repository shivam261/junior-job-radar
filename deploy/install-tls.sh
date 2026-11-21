#!/usr/bin/env bash
# Install the three ACM exports without displaying a private key or passphrase.
set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
  echo "Run with sudo bash deploy/install-tls.sh /home/ec2-user/launchpad-certs" >&2
  exit 1
fi

cert_source="${1:-/home/ec2-user/launchpad-certs}"
for certificate_file in certificate.pem certificate_chain.pem private_key.pem; do
  if [[ ! -s "$cert_source/$certificate_file" ]]; then
    echo "Missing or empty certificate file: $cert_source/$certificate_file" >&2
    exit 1
  fi
done
if ! getent group launchpad >/dev/null; then
  echo "Run install-native.sh first to create the application account." >&2
  exit 1
fi

umask 077
install -d -o root -g launchpad -m 0750 /etc/launchpad
tls_stage=$(mktemp -d /etc/launchpad/.tls-stage.XXXXXX)
trap 'rm -rf -- "$tls_stage"' EXIT

openssl x509 -in "$cert_source/certificate.pem" -noout -checkhost radar.shivam-tripathi.com
openssl x509 -in "$cert_source/certificate.pem" -noout -checkend 86400
openssl verify -purpose sslserver -verify_hostname radar.shivam-tripathi.com \
  -untrusted "$cert_source/certificate_chain.pem" "$cert_source/certificate.pem"

echo "If prompted, enter the ACM export passphrase (it will not be displayed)."
openssl pkey -in "$cert_source/private_key.pem" -out "$tls_stage/server-key.pem"
cat "$cert_source/certificate.pem" "$cert_source/certificate_chain.pem" > "$tls_stage/fullchain.pem"

certificate_digest=$(openssl x509 -in "$cert_source/certificate.pem" -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum)
private_key_digest=$(openssl pkey -in "$tls_stage/server-key.pem" -pubout -outform DER | sha256sum)
if [[ "$certificate_digest" != "$private_key_digest" ]]; then
  echo "The certificate and private key do not match; existing TLS files were preserved." >&2
  exit 1
fi

# Use one directory per certificate and atomically switch the symlink. Existing
# Uvicorn processes keep their loaded certificate until the operator restarts.
tls_release="/etc/launchpad/tls-$(date -u +%Y%m%dT%H%M%S)-$$"
install -d -o root -g launchpad -m 0750 "$tls_release"
install -o root -g launchpad -m 0640 "$tls_stage/fullchain.pem" "$tls_release/fullchain.pem"
install -o root -g launchpad -m 0640 "$tls_stage/server-key.pem" "$tls_release/server-key.pem"
if [[ -e /etc/launchpad/tls && ! -L /etc/launchpad/tls ]]; then
  echo "/etc/launchpad/tls already exists as a directory; move it aside before installing." >&2
  exit 1
fi
ln -s "$tls_release" "$tls_stage/current"
mv -Tf "$tls_stage/current" /etc/launchpad/tls
echo "Verified and installed the certificate for radar.shivam-tripathi.com."
