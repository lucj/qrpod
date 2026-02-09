# Scan Me Maybe: QR-Driven Pod Scaling with Karpenter on Exoscale

A demo application for Kubernetes that displays a QR code on a big screen. When participants scan it with their phones, it creates 1-10 random pods and shows a visual icon that inflates as pods scale up. Perfect for presentations and demos showcasing Karpenter node autoscaling.

## Features

- **Big Screen Display** - Shows QR code, live visualization, pod count, and node count
- **Mobile Result Page** - Participants see "WOW! You created X Pods" after scanning
- **Real-time Updates** - Metrics update every 3 seconds
- **Visual Scaling** - Icon grows 10% per pod created (max 5x)
- **Token Security** - Basic authentication to prevent abuse

## Architecture

- **Backend:** Python/Flask with Kubernetes Python client
- **Frontend:** HTML/CSS/JavaScript with QRCode.js
- **Two Pages:**
  - `/` - Big screen display with QR code and live metrics
  - `/scan?token=X` - Mobile result page after scanning

## Quick Start

### 1. Generate and Configure Token

```bash
# Generate token
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Encode to base64
echo -n "YOUR_TOKEN" | base64

# Update kubernetes/secret.yaml with the base64 value
```

### 2. Build and Push Image

```bash
docker build -t qr-app:latest .

# If using remote registry:
docker tag qr-app:latest YOUR_REGISTRY/qr-app:latest
docker push YOUR_REGISTRY/qr-app:latest
```

Update `image` in `kubernetes/app-deployment.yaml` if using remote registry.

### 3. Deploy to Kubernetes

```bash
kubectl apply -f kubernetes/rbac.yaml
kubectl apply -f kubernetes/secret.yaml
kubectl apply -f kubernetes/app-deployment.yaml
kubectl apply -f kubernetes/app-service.yaml
```

### 4. Get External IP and Update APP_URL

```bash
kubectl get service qr-app

# Update APP_URL with external IP
kubectl set env deployment/qr-app APP_URL=http://YOUR_EXTERNAL_IP
```

### 5. Open on Big Screen

Navigate to `http://YOUR_EXTERNAL_IP` on your presentation display.

## Usage Flow

1. **Display big screen** showing QR code, visualization, and metrics
2. **Participants scan QR code** with their mobile devices
3. **System creates 1-10 random pods** in the cluster
4. **Mobile shows result:** "WOW! You created X Pods" with pod names
5. **Big screen updates live:** Pod count, node count (if Karpenter scales), and icon inflates

## Local Development

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
export AUTH_TOKEN="test-token-123"
export NAMESPACE="default"
export APP_URL="http://localhost:5000"

# Run application
python app/main.py
```

For local Kubernetes testing with kind:

```bash
kind create cluster
docker build -t qr-app:latest .
kind load docker-image qr-app:latest
kubectl apply -f kubernetes/
kubectl port-forward service/qr-app 5000:80
```

## Configuration

Environment variables in `kubernetes/app-deployment.yaml`:

- `AUTH_TOKEN` - Secret token for authentication (from Secret)
- `NAMESPACE` - Kubernetes namespace (default: `default`)
- `APP_URL` - Public URL for QR code generation

## API Endpoints

- `GET /` - Big screen display page
- `GET /scan?token=X` - Mobile result page (creates pods)
- `GET /api/pod-count` - Returns current pod count
- `GET /api/node-count` - Returns current node count
- `GET /health` - Health check

## Cleanup

```bash
# Delete created pods
kubectl delete pods -l app=qr-scaling-demo

# Remove application
kubectl delete -f kubernetes/
```

## Troubleshooting

**Pods not being created:**
```bash
kubectl auth can-i create pods --as=system:serviceaccount:default:qr-app-sa
kubectl logs deployment/qr-app
```

**Node count not updating:**
```bash
kubectl auth can-i list nodes --as=system:serviceaccount:default:qr-app-sa
```

**Metrics not updating:**
- Check `/api/pod-count` and `/api/node-count` endpoints
- Verify pods have label `app=qr-scaling-demo`
- Check browser console for errors

## Project Structure

```
exo-qrpods/
├── app/
│   ├── main.py              # Flask application with routes
│   ├── k8s_manager.py       # Kubernetes API integration
│   ├── config.py            # Configuration management
│   ├── auth.py              # Token authentication
│   └── static/
│       ├── css/style.css    # Big screen styling
│       └── js/app.js        # Polling and animations
├── templates/
│   ├── index.html           # Big screen display
│   └── scan-result.html     # Mobile result page
├── kubernetes/
│   ├── rbac.yaml            # RBAC (pod + node permissions)
│   ├── secret.yaml          # Auth token
│   ├── app-deployment.yaml  # Deployment manifest
│   └── app-service.yaml     # LoadBalancer service
└── Dockerfile
```

## License

MIT
