#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="flask-web"
ACR_NAME="stevedevopslab6280"
ENV_FILE="/etc/flask-web/flask-web.env"
PREVIOUS_IMAGE_FILE="/var/lib/flask-web/previous-image"

echo "========================================="
echo "Starting external deployment rollback"
echo "========================================="

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: Environment file not found:"
    echo "  ${ENV_FILE}"
    exit 1
fi

if [[ ! -s "${PREVIOUS_IMAGE_FILE}" ]]; then
    echo "ERROR: No previous image has been recorded."
    exit 1
fi

PREVIOUS_IMAGE=$(cat "${PREVIOUS_IMAGE_FILE}")

if [[ -z "${PREVIOUS_IMAGE}" ]]; then
    echo "ERROR: Previous image value is empty."
    exit 1
fi

CURRENT_IMAGE=""

if docker inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
    CURRENT_IMAGE=$(docker inspect \
        --format='{{.Config.Image}}' \
        "${CONTAINER_NAME}")

    echo "Failed image:"
    echo "  ${CURRENT_IMAGE}"
fi

echo "Restoring previous image:"
echo "  ${PREVIOUS_IMAGE}"

az login --identity --allow-no-subscriptions >/dev/null
az acr login --name "${ACR_NAME}"

docker pull "${PREVIOUS_IMAGE}"

docker logs "${CONTAINER_NAME}" 2>/dev/null || true
docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

docker run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    --env-file "${ENV_FILE}" \
    -p 5000:5000 \
    "${PREVIOUS_IMAGE}"

echo "Waiting for restored application..."

for i in {1..30}; do
    if curl -fsS http://127.0.0.1:5000/health >/dev/null; then
        echo
        echo "Rollback successful."
        echo "Restored image:"
        echo "  ${PREVIOUS_IMAGE}"
        exit 0
    fi

    echo "Rollback health check attempt ${i}/30 failed."
    sleep 2
done

echo "ERROR: The previous image was restored but did not become healthy."

docker logs "${CONTAINER_NAME}" 2>/dev/null || true

exit 1
