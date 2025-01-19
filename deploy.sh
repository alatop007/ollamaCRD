docker build -t webcodes0071/ollama-operator:latest .
docker push webcodes0071/ollama-operator:latest
kubectl apply -f manifests/crd.yaml
kubectl apply -f manifests/deployment.yaml
kubectl apply -f manifests/mistral.yaml