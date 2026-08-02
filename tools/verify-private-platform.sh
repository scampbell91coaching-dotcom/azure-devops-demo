#!/usr/bin/env bash
set -Eeuo pipefail

kubectl rollout status deploy/platform-portal-private -n production --timeout=2m
kubectl rollout status deploy/platform-oauth2-proxy -n production --timeout=2m

curl -fsS --max-time 15 -o /dev/null   -w 'Hip guide HTTP %{http_code}\n'   https://traditionalstrength.co.uk/guides/hip-pain

curl -fsS --max-time 15 -o /dev/null   -w 'Shoulder guide HTTP %{http_code}\n'   https://traditionalstrength.co.uk/guides/shoulder-pain

kubectl run verify-private-portal -n production --rm -i --restart=Never   --image=curlimages/curl --   curl -fsS --max-time 10 http://platform-portal-private/health

echo

kubectl run verify-oauth2 -n production --rm -i --restart=Never   --image=curlimages/curl --   curl -fsS --max-time 10 http://platform-oauth2-proxy:4180/ping

echo

kubectl get certificate platform-traditionalstrength-tls -n production
kubectl get pvc platform-portal-private-data -n production

curl -sS --max-time 15 -o /dev/null   -w 'Private anonymous HTTP %{http_code}\nRedirect %{redirect_url}\n'   https://platform.traditionalstrength.co.uk/
