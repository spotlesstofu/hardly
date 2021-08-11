#!/usr/bin/bash

source /usr/bin/setup_env_in_openshift.sh

mkdir --mode=0700 -p "${PACKIT_HOME}/.ssh"
grep -q gitlab.com "${PACKIT_HOME}/.ssh/known_hosts" || ssh-keyscan gitlab.com >>"${PACKIT_HOME}/.ssh/known_hosts"

run_worker_.sh
