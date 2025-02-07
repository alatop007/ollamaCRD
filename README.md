Todo 

<!-- 1. fix logging -->
2. documentation
3. testing
<!-- 4. multi-stage dockerfile -->
<!-- 5. deploy script -->
6. helm chart
<!-- 7. make value.yaml deployment and able to specify replicas -->
8. ability to run local image and not pull from internet
<!-- 9. model service as a deployment -->

## Usage

This project allows you to easily deploy and manage AI models in a Kubernetes environment.

### Prerequisites

- Kubernetes cluster
- kubectl configured to access your cluster

### Deploying a Multi-Model and able to access it via different services

1. Create a YAML file for your model (e.g., `manifests/deepseek.yaml`):

```yaml
name: deepseek-coder-33b
model:
  type: deepseek
  path: deepseek-ai/deepseek-coder-33b-instruct
resources:
  requests:
    cpu: "4"
    memory: "32Gi"
  limits:
    cpu: "8"
    memory: "64Gi"
```

2. Deploy the model using the deploy script:

```bash
./deploy.sh 
```

This will:
- Create necessary Kubernetes resources
- Deploy the model service
- Configure the model with specified resources
- Set up the service endpoints
```

### Configuration Options

Key parameters in the model YAML:
- `name`: Unique identifier for your model deployment
- `model.type`: Type of model (e.g., deepseek, llama, etc.)
- `resources`: CPU and memory specifications for the model container