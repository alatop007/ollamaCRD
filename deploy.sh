#!/bin/bash
export IMAGE_TAG="v0.0.1"        
export NAMESPACE="default"       
export MODELS="deepseek,llama"  
export PORT="11435"              
export MODEL_FOR_PORT_FORWARD="deepseek" 
export ENABLE_PORT_FORWARD="false" 

IMAGE_REGISTRY="webcodes0071"
IMAGE_NAME="ollama-operator"
IMAGE_TAG=${IMAGE_TAG:-"latest"} 
NAMESPACE=${NAMESPACE:-"default"} 
MODELS=${MODELS:-"deepseek,llama"}
PORT=${PORT:-"11434"}
MODEL_FOR_PORT_FORWARD=${MODEL_FOR_PORT_FORWARD:-"deepseek"}
ENABLE_PORT_FORWARD=${ENABLE_PORT_FORWARD:-"false"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' 

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to check if command exists
check_command() {
    if ! command -v $1 &> /dev/null; then
        print_error "$1 is required but not installed."
        exit 1
    fi
}

check_command docker
check_command kubectl


build_and_push() {
    print_status "Building Docker image ${IMAGE_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
    if docker build -t ${IMAGE_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG} .; then
        print_status "Docker image built successfully"
    else
        print_error "Docker build failed"
        exit 1
    fi

    print_status "Pushing Docker image to registry"
    if docker push ${IMAGE_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}; then
        print_status "Docker image pushed successfully"
    else
        print_error "Docker push failed"
        exit 1
    fi
}

# Deploy Kubernetes resources
deploy_resources() {
    print_status "Deploying CRD"
    kubectl apply -f manifests/crd.yaml

    print_status "Deploying operator"
    kubectl apply -f manifests/deployment.yaml
    print_status "Waiting for operator pod to be ready..."
    while true; do
        POD_STATUS=$(kubectl get pods -l app=ollama-operator -n default -o jsonpath='{.items[0].status.phase}' 2>/dev/null)
        if [ "$POD_STATUS" = "Running" ]; then
            print_status "Operator pod is running"
            break
        elif [ "$POD_STATUS" = "Error" ] || [ "$POD_STATUS" = "Failed" ]; then
            print_error "Operator pod failed to start"
            exit 1
        fi
        sleep 5
    done

    # Deploy selected models
    IFS=',' read -ra MODEL_ARRAY <<< "$MODELS"
    for model in "${MODEL_ARRAY[@]}"; do
        if [ -f "manifests/${model}.yaml" ]; then
            print_status "Deploying ${model} model"
            kubectl apply -f manifests/${model}.yaml
        else
            print_warning "Model file manifests/${model}.yaml not found"
        fi
    done
}

# Setup port forwarding
setup_port_forward() {
    if [ "${ENABLE_PORT_FORWARD}" = "true" ]; then
        print_status "Setting up port forwarding for ${MODEL_FOR_PORT_FORWARD} model"
        print_status "Port forwarding will be set to ${PORT}"
        kubectl port-forward pods/ollama-${MODEL_FOR_PORT_FORWARD} ${PORT}:${PORT} -n ${NAMESPACE}
    else
        print_status "Port forwarding is disabled"
    fi
}

# Function to cleanup all deployed resources
cleanup_resources() {
    print_status "Starting cleanup of all deployed resources"

    # Remove model deployments first
    IFS=',' read -ra MODEL_ARRAY <<< "$MODELS"
    for model in "${MODEL_ARRAY[@]}"; do
        if [ -f "manifests/${model}.yaml" ]; then
            print_status "Removing ${model} model"
            kubectl delete -f manifests/${model}.yaml --ignore-not-found=true
        fi
    done

    # Remove operator deployment
    print_status "Removing operator deployment"
    kubectl delete -f manifests/deployment.yaml --ignore-not-found=true

    # Remove CRD last
    print_status "Removing CRD"
    kubectl delete -f manifests/crd.yaml --ignore-not-found=true

    print_status "Cleanup completed"
}

# Main execution
main() {
    if [ "$1" = "cleanup" ]; then
        # Ask for confirmation before cleanup
        read -p "This will remove all deployed resources. Continue? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_status "Cleanup cancelled"
            exit 1
        fi
        cleanup_resources
        exit 0
    fi

    # Show configuration
    print_status "Deploying with configuration:"
    echo "Image: ${IMAGE_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
    echo "Namespace: ${NAMESPACE}"
    echo "Models to deploy: ${MODELS}"
    if [ "${ENABLE_PORT_FORWARD}" = "true" ]; then
        echo "Port forwarding: ${PORT} for ${MODEL_FOR_PORT_FORWARD}"
    else
        echo "Port forwarding: Disabled"
    fi
    echo

    # Ask for confirmation
    read -p "Continue with deployment? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Deployment cancelled"
        exit 1
    fi
    # Check if image exists locally
    if docker image inspect "${IMAGE_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}" >/dev/null 2>&1; then
        print_status "Image ${IMAGE_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG} already exists locally, skipping build"
    else
        build_and_push
    fi
    deploy_resources
    setup_port_forward
}

main "$@"

