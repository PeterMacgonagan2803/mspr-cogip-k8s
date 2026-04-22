#!/bin/bash
set -e
cd /root/mspr-cogip-k8s/ansible
ansible-playbook playbooks/site.yml -v > /tmp/mspr-ap.log 2>&1
echo True > /tmp/mspr-ap.rc
