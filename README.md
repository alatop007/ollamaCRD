# Ollama Kubernetes Operator

A Kubernetes operator for deploying and managing Ollama LLM models in your cluster.

## Todo 

<!-- 1. fix logging -->
2. documentation
3. testing
<!-- 4. multi-stage dockerfile -->
<!-- 5. deploy script -->
6. helm chart
<!-- 7. make value.yaml deployment and able to specify replicas -->
<!-- 8. ability to run local image and not pull from internet -->
<!-- 9. model service as a deployment -->
<!-- 10. Allow KUBECONFIG to be passed in -->
11. Allow local model to be used

## Project Structure

```
.
├── controller.py                  # Main operator logic
├── Dockerfile                     # Multi-stage build for operator
├── deploy.sh                      # Deployment script
├── manifests/
│   ├── operators/                
│   │   ├── crd.yaml               # Custom Resource Definition
│   │   ├── deployment.yaml        # Operator deployment
│   │   └── rbac.yaml              # RBAC configuration
│   └── values/                  
│       ├── deepseek.yaml          # DeepSeek model config
│       ├── mistral.yaml           # Mistral model config
│       └── llama.yaml             # Llama model config
```

## Prerequisites

- Kubernetes cluster
- kubectl configured to access your cluster
- Docker for building images
- Valid kubeconfig file

## Configuration

### Environment Variables

The following environment variables can be configured:

```bash
export IMAGE_TAG="latest"        # Version of the operator image
export NAMESPACE="default"       # Kubernetes namespace
export MODELS="deepseek,llama"  # Comma-separated list of models to deploy
export PORT="11435"             # Port for forwarding
export MODEL_FOR_PORT_FORWARD="deepseek"  # Model to port-forward
export ENABLE_PORT_FORWARD="false"  # Enable/disable port forwarding
export KUBECONFIG="$HOME/.kube/config"  # Path to kubeconfig file
```

### KUBECONFIG Configuration

You can specify which Kubernetes cluster to use in several ways:

1. Use the default local config:
```bash
./deploy.sh
```

2. Specify a different kubeconfig file:
```bash
KUBECONFIG=/path/to/different/config ./deploy.sh
```

3. Export in your environment:
```bash
export KUBECONFIG=/path/to/your/kubeconfig
./deploy.sh
```

## Usage

### Deploying Models

1. Create a YAML file for your model in `manifests/values/` (e.g., `manifests/values/deepseek.yaml`):

```yaml
apiVersion: example.com/v1
kind: OllamaModel
metadata:
  name: deepseek
spec:
  modelName: deepseek-coder:33b
  replicas: 1
  service:
    type: ClusterIP
    port: 11434
    name: deepseek-service
  resources:
    requests:
      cpu: "4"
      memory: "32Gi"
    limits:
      cpu: "8"
      memory: "64Gi"
```

2. Deploy using the script:
```bash
./deploy.sh
```

### Cleanup

To remove all deployed resources:
```bash
./deploy.sh cleanup
```

## Accessing the Models

### Within the Cluster

Models are accessible via their service names within the cluster:

```bash
curl http://deepseek-service:11434/api/chat -d '{
  "model": "deepseek-coder:33b",
  "messages": [
    { "role": "user", "content": "Write a Python function to calculate fibonacci numbers" }
  ]
}'
```

### External Access

Three options for external access:

1. LoadBalancer:
```yaml
spec:
  service:
    type: LoadBalancer
    port: 11434
```

2. NodePort:
```yaml
spec:
  service:
    type: NodePort
    port: 11434
```

3. Port-forwarding (for testing):
```bash
ENABLE_PORT_FORWARD="true" PORT="11434" MODEL_FOR_PORT_FORWARD="deepseek" ./deploy.sh
```

## Service Types

- `ClusterIP`: Internal cluster access only
- `NodePort`: Exposes on each node's IP
- `LoadBalancer`: Creates external load balancer

## Development

### Building the Operator

```bash
docker build -t webcodes0071/ollama-operator:v0.0.2 .
```

### Local Testing

1. Run with local config:
```bash
KUBECONFIG=$HOME/.kube/config ./deploy.sh
```

2. Enable port forwarding for testing:
```bash
ENABLE_PORT_FORWARD="true" ./deploy.sh
```

## Troubleshooting

1. Check operator logs:
```bash
kubectl logs -f deployment/ollama-operator
```

2. Check model pods:
```bash
kubectl get pods -l app=ollama
```

3. KUBECONFIG issues:
```bash
# Verify kubeconfig
kubectl --kubeconfig=$KUBECONFIG cluster-info
```

## Contributing

1. Fork the repository
2. Create your feature branch
3. Make your changes
4. Submit a pull request
