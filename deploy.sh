docker build -t webcodes0071/ollama-operator:latest .
docker push webcodes0071/ollama-operator:latest
kubectl apply -f manifests/crd.yaml
kubectl apply -f manifests/deployment.yaml
kubectl apply -f manifests/mistral.yaml
kubectl apply -f manifests/llama.yaml
kubectl port-forward pods/ollama-service-mistral 11434:11434 -n default
curl localhost:11434/api/version
