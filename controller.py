import kopf
import kubernetes
import time
from kubernetes.client import (
    V1Pod,
    V1ObjectMeta,
    V1PodSpec,
    V1Container,
    V1ContainerPort,
    V1Volume,
    V1VolumeMount,
    V1EmptyDirVolumeSource,
    V1EnvVar,
    ApiException
)

# Initialize Kubernetes client
kubernetes.config.load_incluster_config()
core_api = kubernetes.client.CoreV1Api()

def create_ollama_pod(name, namespace, model_name):
    """Create a pod running Ollama service that pulls the model on startup."""
    return V1Pod(
        metadata=V1ObjectMeta(
            name=f"ollama-{name}",
            namespace=namespace,
            labels={
                'app': 'ollama',
                'model': name
            }
        ),
        spec=V1PodSpec(
            containers=[
                V1Container(
                    name='ollama',
                    image='ollama/ollama:latest',
                    ports=[V1ContainerPort(container_port=11434)],
                    volume_mounts=[
                        V1VolumeMount(
                            name='ollama-data',
                            mount_path='/root/.ollama'  # Changed back to /root
                        )
                    ],
                    command=['sh', '-c'],
                    args=[
                        'ollama serve & '
                        f'sleep 5 && '
                        f'ollama pull {model_name} && '
                        f'wait'
                    ],
                    resources={
                        'requests': {
                            'cpu': '500m',
                            'memory': '1Gi'
                        },
                        'limits': {
                            'cpu': '2',
                            'memory': '4Gi'
                        }
                    },
                    readiness_probe={
                        'httpGet': {
                            'path': '/api/version',
                            'port': 11434
                        },
                        'initialDelaySeconds': 5,
                        'periodSeconds': 10
                    },
                    liveness_probe={
                        'httpGet': {
                            'path': '/api/version',
                            'port': 11434
                        },
                        'initialDelaySeconds': 15,
                        'periodSeconds': 20
                    }
                )
            ],
            volumes=[
                V1Volume(
                    name='ollama-data',
                    empty_dir=V1EmptyDirVolumeSource()
                )
            ],
            security_context={
                'runAsUser': 0,  # Run as root
                'runAsGroup': 0,
                'fsGroup': 0,
                'runAsNonRoot': False  # Allow running as root
            }
        )
    )


def get_pod_status(name, namespace):
    """Get the current status of a pod."""
    try:
        pod = core_api.read_namespaced_pod(name=name, namespace=namespace)
        return {
            'phase': pod.status.phase,
            'ready': all(
                container.ready 
                for container in (pod.status.container_statuses or [])
            )
        }
    except ApiException as e:
        if e.status == 404:
            return {'phase': 'NotFound', 'ready': False}
        raise

def wait_for_pod_ready(name, namespace, timeout=300):
    """Wait for a pod to be ready with exponential backoff."""
    start = time.time()
    backoff = 1
    max_backoff = 32

    while time.time() - start < timeout:
        try:
            status = get_pod_status(name, namespace)
            if status['phase'] == 'Running' and status['ready']:
                return True
            
            if status['phase'] in ['Failed', 'Unknown']:
                return False
                
        except ApiException as e:
            if e.status != 404:
                raise
        
        time.sleep(min(backoff, max_backoff))
        backoff *= 2
    
    return False

@kopf.on.create('example.com', 'v1', 'ollamamodels')
def create_fn(spec, name, namespace, logger, patch, **kwargs):
    try:
        model_name = spec.get('modelName')
        if not model_name:
            raise kopf.PermanentError("modelName must be specified in spec")

        pod = create_ollama_pod(name, namespace, model_name)
        
        try:
            created_pod = core_api.create_namespaced_pod(
                namespace=namespace, 
                body=pod
            )
            
            patch.status['phase'] = 'Creating'
            patch.status['pod_name'] = created_pod.metadata.name
            patch.status['model'] = model_name
            
        except ApiException as e:
            if e.status == 409:
                logger.info(f"Pod {pod.metadata.name} already exists")
                patch.status['phase'] = 'Exists'
                return
            raise kopf.PermanentError(f"Failed to create pod: {e}")

        if not wait_for_pod_ready(pod.metadata.name, namespace):
            try:
                core_api.delete_namespaced_pod(
                    name=pod.metadata.name,
                    namespace=namespace
                )
            except ApiException:
                pass
            patch.status['phase'] = 'Failed'
            raise kopf.PermanentError("Timeout waiting for Ollama pod to be ready")

        patch.status['phase'] = 'Running'
        patch.status['ready'] = True

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        patch.status['phase'] = 'Error'
        patch.status['error'] = str(e)
        raise kopf.PermanentError(f"Failed to create Ollama model: {str(e)}")

@kopf.on.update('example.com', 'v1', 'ollamamodels')
def update_fn(spec, name, namespace, logger, patch, **kwargs):
    """Handle updates to the OllamaModel resource."""
    pod_name = f"ollama-{name}"
    try:
        current_status = get_pod_status(pod_name, namespace)
        patch.status['phase'] = current_status['phase']
        patch.status['ready'] = current_status['ready']
    except ApiException as e:
        logger.error(f"Error updating status: {e}")
        patch.status['phase'] = 'Error'
        patch.status['error'] = str(e)

@kopf.on.delete('example.com', 'v1', 'ollamamodels')
def delete_fn(spec, name, namespace, logger, **kwargs):
    """Handler for deleting OllamaModel resources."""
    pod_name = f"ollama-{name}"
    try:
        core_api.delete_namespaced_pod(
            name=pod_name,
            namespace=namespace
        )
        logger.info(f"Deleted pod {pod_name}")
    except ApiException as e:
        if e.status != 404:
            logger.error(f"Error deleting pod {pod_name}: {e}")
            raise
        logger.warning(f"Pod {pod_name} not found or already deleted")
