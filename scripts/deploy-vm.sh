#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:?Usage: deploy-vm.sh <image>}"

CONTAINER_NAME="flask-web"
ACR_NAME="stevedevopslab6280"
ENV_FILE="/etc/flask-web/flask-web.env"

echo "========================================="
echo "Deploying image:"
echo "  ${IMAGE}"
echo "========================================="

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: Environment file not found:"
    echo "  ${ENV_FILE}"
    exit 1
fi

echo "Logging into Azure with Managed Identity..."
az login --identity --allow-no-subscriptions >/dev/null

echo "Logging into Azure Container Registry..."
az acr login --name "${ACR_NAME}"

echo "Pulling image..."
docker pull "${IMAGE}"

PREVIOUS_IMAGE=""
if docker inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
    PREVIOUS_IMAGE=$(docker inspect \
        --format='{{.Config.Image}}' \
        "${CONTAINER_NAME}")

    echo "Previous image:"
    echo "  ${PREVIOUS_IMAGE}"

    docker stop "${CONTAINER_NAME}" || true
    docker rm "${CONTAINER_NAME}" || true
fi

rollback() {
    echo
    echo "Deployment failed."

    docker logs "${CONTAINER_NAME}" 2>/dev/null || true
    docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

    if [[ -n "${PREVIOUS_IMAGE}" ]]; then
        echo "Rolling back to:"
        echo "  ${PREVIOUS_IMAGE}"

        docker run -d \
            --name "${CONTAINER_NAME}" \
            --restart unless-stopped \
            --env-file "${ENV_FILE}" \
            -p 5000:5000 \
            "${PREVIOUS_IMAGE}"
    fi

    exit 1
}

echo "Starting new container..."

docker run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    --env-file "${ENV_FILE}" \
    -p 5000:5000 \
    "${IMAGE}"

echo
echo "Waiting for application..."

for i in {1..30}; do

    if curl -fsS http://127.0.0.1:5000/health >/dev/null; then
        echo
        echo "Deployment successful."

        docker image prune -f

        exit 0
    fi

    sleep 2
done

rollback
