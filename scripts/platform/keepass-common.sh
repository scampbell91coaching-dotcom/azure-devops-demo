#!/usr/bin/env bash
# Shared KeePass operations definitions. Source this file; do not execute it.

# shellcheck disable=SC2034 # Consumed by scripts that source this library.
KEEPASS_GROUPS=(
  "00 - Recovery"
  "01 - GitHub" "01 - GitHub/Account" "01 - GitHub/Personal Access Tokens"
  "01 - GitHub/Repository Secrets" "01 - GitHub/Repository Variables"
  "02 - Azure" "02 - Azure/Account" "02 - Azure/Subscription"
  "02 - Azure/Service Principals" "02 - Azure/Managed Identities" "02 - Azure/Resource Access"
  "03 - Kubernetes" "03 - Kubernetes/AKS" "03 - Kubernetes/kubeconfig"
  "03 - Kubernetes/Registry Credentials"
  "04 - Database" "04 - Database/PostgreSQL" "04 - Database/Local Development"
  "05 - Terraform" "05 - Terraform/State Backend" "05 - Terraform/Environment Variables"
  "06 - SSH" "07 - DNS and Domains" "08 - Newie" "09 - Local Development"
  "99 - Retired Credentials"
)

# shellcheck disable=SC2034 # Consumed by scripts that source this library.
KEEPASS_METADATA_ENTRIES=("00 - Recovery/KeePass Database Recovery")

keepass_require_database() {
  local database=$1
  if [[ ! -f "$database" ]]; then
    printf 'ERROR: KeePass database not found: %s\n' "$database" >&2
    return 1
  fi
  command -v keepassxc-cli >/dev/null 2>&1 || {
    printf 'ERROR: keepassxc-cli is required.\n' >&2
    return 1
  }
}

keepass_read_password() {
  if [[ ! -r /dev/tty ]]; then
    printf 'ERROR: a controlling terminal is required for the master password.\n' >&2
    return 1
  fi
  IFS= read -r -s -p 'Enter KeePass master password: ' KEEPASS_MASTER_PASSWORD </dev/tty
  printf '\n' >/dev/tty
  [[ -n "$KEEPASS_MASTER_PASSWORD" ]] || {
    printf 'ERROR: the master password cannot be empty.\n' >&2
    return 1
  }
}

keepass_cli() {
  printf '%s\n' "$KEEPASS_MASTER_PASSWORD" | keepassxc-cli "$@"
}

keepass_forget_password() {
  unset KEEPASS_MASTER_PASSWORD
}
