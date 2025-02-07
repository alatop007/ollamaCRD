import kopf
import kubernetes
import time
import logging
import re
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
    ApiException,
    V1Deployment,
    V1DeploymentSpec,
    V1LabelSelector,
    V1Service,
    V1ServiceSpec,
    V1ServicePort
)

# Initialize Kubernetes client
kubernetes.config.load_incluster_config()
core_api = kubernetes.client.CoreV1Api()
apps_api = kubernetes.client.AppsV1Api()

def sanitize_label(value):
    """Sanitize a value to be used as a Kubernetes label.
    Only allows alphanumeric characters, '-', '_' or '.'"""
    # Replace invalid characters with '-'
    sanitized = re.sub(r'[^a-zA-Z0-9\-_\.]', '-', value)
    # Ensure it starts and ends with alphanumeric
    if not sanitized[0].isalnum():
        sanitized = 'x' + sanitized
    if not sanitized[-1].isalnum():
        sanitized = sanitized + 'x'
    return sanitized

def create_ollama_deployment(name, namespace, spec):
    """Create a deployment and service for Ollama."""
    model_name = spec['modelName']
    replicas = spec.get('replicas', 1)
    
    # Sanitize model name for use in labels
    sanitized_model_name = sanitize_label(model_name)
    sanitized_name = sanitize_label(name)
    
    # Get configurations with defaults
    resources = spec.get('resources', {
        'requests': {'cpu': '500m', 'memory': '1Gi'},
        'limits': {'cpu': '2', 'memory': '4Gi'}
    })
    
    # Get service configurations
    service_config = spec.get('service', {
        'type': 'ClusterIP',
        'port': 11434,
        'name': f"ollama-{sanitized_name}-{sanitized_model_name}"
    })
    
    image = spec.get('image', 'ollama/ollama:latest')
    
    probes = spec.get('probes', {
        'readiness': {
            'initialDelaySeconds': 5,
            'periodSeconds': 10
        },
        'liveness': {
            'initialDelaySeconds': 15,
            'periodSeconds': 20
        }
    })
    
    volume_mounts = spec.get('volumeMounts', [
        {'name': 'ollama-data', 'mountPath': '/root/.ollama'}
    ])

    # Create labels that will be used by both deployment and service
    labels = {
        'app': 'ollama',
        'model': sanitized_name,
        'modelName': sanitized_model_name
    }

    # Create a service name from config or use default
    service_name = service_config.get('name', f"ollama-{sanitized_name}-{sanitized_model_name}")

    # Define the deployment
    deployment = V1Deployment(
        metadata=V1ObjectMeta(
            name=f"ollama-{sanitized_name}",
            namespace=namespace,
            labels=labels,
            annotations={
                'originalModelName': model_name,
                'modelInstance': name
            }
        ),
        spec=V1DeploymentSpec(
            replicas=replicas,
            selector=V1LabelSelector(
                match_labels=labels
            ),
            template={
                'metadata': {
                    'labels': labels,
                    'annotations': {
                        'originalModelName': model_name
                    }
                },
                'spec': {
                    'containers': [{
                        'name': 'ollama',
                        'image': image,
                        'ports': [{'containerPort': 11434}],
                        'volumeMounts': [
                            {
                                'name': mount['name'],
                                'mountPath': mount['mountPath']
                            } for mount in volume_mounts
                        ],
                        'command': ['sh', '-c'],
                        'args': [
                            'ollama serve & '
                            f'sleep 5 && '
                            f'ollama pull {model_name} && '
                            f'wait'
                        ],
                        'resources': resources,
                        'readinessProbe': {
                            'httpGet': {
                                'path': '/api/version',
                                'port': 11434
                            },
                            'initialDelaySeconds': probes['readiness']['initialDelaySeconds'],
                            'periodSeconds': probes['readiness']['periodSeconds']
                        },
                        'livenessProbe': {
                            'httpGet': {
                                'path': '/api/version',
                                'port': 11434
                            },
                            'initialDelaySeconds': probes['liveness']['initialDelaySeconds'],
                            'periodSeconds': probes['liveness']['periodSeconds']
                        }
                    }],
                    'volumes': [
                        {
                            'name': 'ollama-data',
                            'emptyDir': {}
                        }
                    ],
                    'securityContext': {
                        'runAsUser': 0,
                        'runAsGroup': 0,
                        'fsGroup': 0,
                        'runAsNonRoot': False
                    }
                }
            }
        )
    )

    # Define the service
    service = V1Service(
        metadata=V1ObjectMeta(
            name=service_name,
            namespace=namespace,
            labels=labels,
            annotations={
                'originalModelName': model_name,
                'modelInstance': name
            }
        ),
        spec=V1ServiceSpec(
            selector=labels,
            ports=[
                V1ServicePort(
                    port=service_config.get('port', 11434),
                    target_port=11434,
                    protocol='TCP',
                    name='http'
                )
            ],
            type=service_config.get('type', 'ClusterIP')
        )
    )

    return deployment, service

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
    logger = logging.getLogger(__name__)

    logger.info(f"Waiting for pod {name} to be ready (timeout: {timeout}s)")
    while time.time() - start < timeout:
        try:
            status = get_pod_status(name, namespace)
            logger.debug(f"Pod {name} status: {status}")
            
            if status['phase'] == 'Running' and status['ready']:
                logger.info(f"Pod {name} is ready")
                return True
            
            if status['phase'] in ['Failed', 'Unknown']:
                logger.error(f"Pod {name} entered {status['phase']} state")
                return False
                
        except ApiException as e:
            if e.status != 404:
                logger.error(f"Error checking pod status: {e}")
                raise
            logger.debug(f"Pod {name} not found yet")
        
        wait_time = min(backoff, max_backoff)
        logger.debug(f"Waiting {wait_time}s before next check")
        time.sleep(wait_time)
        backoff *= 2
    
    logger.error(f"Timeout waiting for pod {name} to be ready")
    return False

def wait_for_deployment_ready(name, namespace, timeout=300):
    """Wait for a deployment to be ready with exponential backoff."""
    apps_api = kubernetes.client.AppsV1Api()
    start = time.time()
    backoff = 1
    max_backoff = 32
    logger = logging.getLogger(__name__)

    logger.info(f"Waiting for deployment {name} to be ready (timeout: {timeout}s)")
    while time.time() - start < timeout:
        try:
            deployment = apps_api.read_namespaced_deployment(name=name, namespace=namespace)
            if deployment.status.ready_replicas == deployment.spec.replicas:
                logger.info(f"Deployment {name} is ready")
                return True
                
        except ApiException as e:
            if e.status != 404:
                logger.error(f"Error checking deployment status: {e}")
                raise
            logger.debug(f"Deployment {name} not found yet")
        
        wait_time = min(backoff, max_backoff)
        logger.debug(f"Waiting {wait_time}s before next check")
        time.sleep(wait_time)
        backoff *= 2
    
    logger.error(f"Timeout waiting for deployment {name} to be ready")
    return False

def cleanup_resources(name, namespace, logger):
    """Clean up deployment and service resources."""
    apps_api = kubernetes.client.AppsV1Api()
    try:
        apps_api.delete_namespaced_deployment(
            name=name,
            namespace=namespace
        )
        core_api.delete_namespaced_service(
            name=name,
            namespace=namespace
        )
        logger.info(f"Cleaned up deployment and service {name}")
    except ApiException as e:
        logger.warning(f"Failed to cleanup resources: {e}")

@kopf.on.create('example.com', 'v1', 'ollamamodels')
def create_fn(spec, name, namespace, logger, patch, **kwargs):
    try:
        if not spec.get('modelName'):
            logger.error("modelName not specified in spec")
            raise kopf.PermanentError("modelName must be specified in spec")

        logger.info(f"Creating Ollama deployment for model {spec['modelName']}")
        
        # Create both deployment and service
        deployment, service = create_ollama_deployment(name, namespace, spec)
        
        try:
            # Create the deployment
            created_deployment = apps_api.create_namespaced_deployment(
                namespace=namespace, 
                body=deployment
            )
            logger.info(f"Created deployment {created_deployment.metadata.name}")
            
            # Create the service with model-specific name
            created_service = core_api.create_namespaced_service(
                namespace=namespace,
                body=service
            )
            logger.info(f"Created service {created_service.metadata.name}")
            
            patch.status['phase'] = 'Creating'
            patch.status['deployment_name'] = created_deployment.metadata.name
            patch.status['service_name'] = created_service.metadata.name
            patch.status['model'] = spec['modelName']
            patch.status['created_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            
        except ApiException as e:
            if e.status == 409:
                logger.info(f"Deployment/Service for {name} already exists")
                patch.status['phase'] = 'Exists'
                return
            logger.error(f"Failed to create deployment/service: {e}")
            raise kopf.PermanentError(f"Failed to create deployment/service: {e}")

        # Wait for deployment to be ready
        if not wait_for_deployment_ready(deployment.metadata.name, namespace):
            logger.error(f"Deployment {deployment.metadata.name} failed to become ready")
            cleanup_resources(deployment.metadata.name, namespace, logger)
            patch.status['phase'] = 'Failed'
            raise kopf.PermanentError("Timeout waiting for Ollama deployment to be ready")

        logger.info(f"Successfully deployed Ollama model {spec['modelName']}")
        patch.status['phase'] = 'Running'
        patch.status['ready'] = True
        patch.status['last_updated'] = time.strftime('%Y-%m-%d %H:%M:%S')

    except Exception as e:
        logger.error(f"Unexpected error during creation: {e}", exc_info=True)
        patch.status['phase'] = 'Error'
        patch.status['error'] = str(e)
        patch.status['last_error_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
        raise kopf.PermanentError(f"Failed to create Ollama model: {str(e)}")

@kopf.on.update('example.com', 'v1', 'ollamamodels')
def update_fn(spec, name, namespace, logger, patch, **kwargs):
    """Handle updates to the OllamaModel resource."""
    deployment_name = f"ollama-{name}"
    try:
        current_status = get_pod_status(deployment_name, namespace)
        patch.status['phase'] = current_status['phase']
        patch.status['ready'] = current_status['ready']
    except ApiException as e:
        logger.error(f"Error updating status: {e}")
        patch.status['phase'] = 'Error'
        patch.status['error'] = str(e)

@kopf.on.delete('example.com', 'v1', 'ollamamodels')
def delete_fn(spec, name, namespace, logger, **kwargs):
    """Handler for deleting OllamaModel resources."""
    deployment_name = f"ollama-{name}"
    service_name = f"ollama-{name}-{spec['modelName']}"
    
    try:
        # Delete deployment using apps_api
        apps_api.delete_namespaced_deployment(
            name=deployment_name,
            namespace=namespace
        )
        logger.info(f"Deleted deployment {deployment_name}")
        
        # Delete associated service
        core_api.delete_namespaced_service(
            name=service_name,
            namespace=namespace
        )
        logger.info(f"Deleted service {service_name}")
        
    except ApiException as e:
        if e.status != 404:  # Ignore if already deleted
            logger.error(f"Error deleting resources for {name}: {e}")
            raise
        logger.warning(f"Resources for {name} not found or already deleted")
