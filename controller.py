import kopf
import kubernetes
import time
from kubernetes.client import (
    V1Pod, V1ObjectMeta, V1PodSpec, V1Container, V1EnvVar,
    V1Volume, V1VolumeMount, V1EmptyDirVolumeSource
)

# Configure kubernetes client
kubernetes.config.load_incluster_config()
core_api = kubernetes.client.CoreV1Api()

def wait_for_pod_ready(name, namespace, timeout=300):
    """Wait for pod to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            pod = core_api.read_namespaced_pod(name=name, namespace=namespace)
            if pod.status.phase == 'Running':
                for container_status in pod.status.container_statuses:
                    if container_status.ready:
                        return True
        except kubernetes.client.rest.ApiException:
            pass
        time.sleep(5)
    return False

@kopf.on.create('example.com', 'v1', 'ollamamodels')
def create_fn(spec, name, namespace, logger, **kwargs):
    # Extract model name from spec
    model_name = spec.get('modelName')
    if not model_name:
        raise kopf.PermanentError("modelName must be specified in spec")
    
    # First create the Ollama service pod
    service_pod = create_ollama_service_pod(name, namespace)
    try:
        core_api.create_namespaced_pod(namespace=namespace, body=service_pod)
    except kubernetes.client.rest.ApiException as e:
        if e.status != 409:  # Ignore if pod already exists
            raise kopf.PermanentError(f"Failed to create service pod: {e}")
    
    # Wait for service pod to be ready
    logger.info(f"Waiting for Ollama service pod {service_pod.metadata.name} to be ready...")
    if not wait_for_pod_ready(service_pod.metadata.name, namespace):
        raise kopf.PermanentError("Timeout waiting for Ollama service pod to be ready")
    
    # Create the pull pod
    pull_pod = create_ollama_pull_pod(name, namespace, model_name)
    try:
        core_api.create_namespaced_pod(namespace=namespace, body=pull_pod)
    except kubernetes.client.rest.ApiException as e:
        if e.status != 409:  # Ignore if pod already exists
            raise kopf.PermanentError(f"Failed to create pull pod: {e}")
    
    # Return status
    return {
        'service_pod': service_pod.metadata.name,
        'pull_pod': pull_pod.metadata.name
    }

def create_ollama_service_pod(name, namespace):
    """Create a pod running the Ollama service."""
    return V1Pod(
        metadata=V1ObjectMeta(
            name=f"ollama-service-{name}",
            namespace=namespace,
            labels={
                'app': 'ollama-service',
                'model': name
            }
        ),
        spec=V1PodSpec(
            containers=[
                V1Container(
                    name='ollama',
                    image='ollama/ollama:latest',
                    ports=[{'containerPort': 11434}],
                    volume_mounts=[
                        V1VolumeMount(
                            name='ollama-data',
                            mount_path='/root/.ollama'
                        )
                    ],
                    env=[
                        V1EnvVar(
                            name='OLLAMA_HOST',
                            value='0.0.0.0'
                        )
                    ]
                )
            ],
            volumes=[
                V1Volume(
                    name='ollama-data',
                    empty_dir=V1EmptyDirVolumeSource()
                )
            ]
        )
    )

def create_ollama_pull_pod(name, namespace, model_name):
    """Create a pod for pulling the Ollama model."""
    service_host = f"ollama-service-{name}"
    return V1Pod(
        metadata=V1ObjectMeta(
            name=f"ollama-pull-{name}",
            namespace=namespace,
            labels={
                'app': 'ollama-pull',
                'model': name
            }
        ),
        spec=V1PodSpec(
            containers=[
                V1Container(
                    name='ollama-pull',
                    image='ollama/ollama:latest',
                    command=['sh', '-c'],
                    args=[
                        'apt-get update && apt-get install -y curl && '
                        f'until curl -s http://{service_host}:11434/api/version; do echo "waiting for ollama service"; sleep 2; done && '
                        'echo "Service is ready, starting pull..." && '
                        f'export OLLAMA_HOST=http://{service_host}:11434 && '
                        f'echo "Using OLLAMA_HOST=$OLLAMA_HOST" && '
                        f'ollama pull {model_name}'
                    ],
                    env=[
                        V1EnvVar(
                            name='OLLAMA_HOST',
                            value=f'http://{service_host}:11434'
                        )
                    ]
                )
            ],
            restart_policy='OnFailure'
        )
    )

@kopf.on.delete('example.com', 'v1', 'ollamamodels')
def delete_fn(spec, name, namespace, logger, **kwargs):
    # Clean up both pods if they exist
    for pod_name in [f"ollama-pull-{name}", f"ollama-service-{name}"]:
        try:
            core_api.delete_namespaced_pod(
                name=pod_name,
                namespace=namespace
            )
        except kubernetes.client.rest.ApiException as e:
            if e.status != 404:  # Ignore if pod is already deleted
                raise