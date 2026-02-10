## Scan Me Maybe: QR Code Driven Pod Scaling With Karpenter

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

### Option 1: Deploy with Helm (Recommended)

```bash
# 1. Build and push image
docker build -t qr-app:latest .

# 2. Load to kind (local) or push to registry (remote)
kind load docker-image qr-app:latest
# OR
docker tag qr-app:latest YOUR_REGISTRY/qr-app:latest
docker push YOUR_REGISTRY/qr-app:latest

# 3. Deploy with Helm
helm install qr-pods ./chart

# 4. Get external IP
kubectl get service qr-pods

# 5. Update APP_URL
helm upgrade qr-pods ./chart --set app.url=http://YOUR_EXTERNAL_IP
```

### Option 2: Deploy with Helmfile (Best for automation)

**Method A: Using .env file (Recommended)**

```bash
# 1. Copy example env file and configure
cp .env.example .env
# Edit .env with your values (APP_URL, IMAGE_REPOSITORY, REGISTRY_USERNAME, etc.)

# 2. Deploy with script
./deploy.sh
```

**Method B: Export environment variables**

```bash
# Set all required variables
export APP_URL=http://YOUR_EXTERNAL_IP
export IMAGE_REPOSITORY=ghcr.io/username/qr-app
export REGISTRY_USERNAME=your_github_username
export REGISTRY_PASSWORD=ghp_your_github_token

# Deploy
helmfile sync
```

### Option 3: Manual Kubernetes Manifests

<details>
<summary>Click to expand manual deployment steps</summary>

#### 1. Generate and Configure Token

```bash
# Generate token
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Encode to base64
echo -n "YOUR_TOKEN" | base64

# Update kubernetes/secret.yaml with the base64 value
```

#### 2. Build and Push Image

```bash
docker build -t qr-app:latest .

# If using remote registry:
docker tag qr-app:latest YOUR_REGISTRY/qr-app:latest
docker push YOUR_REGISTRY/qr-app:latest
```

Update `image` in `kubernetes/app-deployment.yaml` if using remote registry.

#### 3. Deploy to Kubernetes

```bash
kubectl apply -f kubernetes/rbac.yaml
kubectl apply -f kubernetes/secret.yaml
kubectl apply -f kubernetes/app-deployment.yaml
kubectl apply -f kubernetes/app-service.yaml
```

#### 4. Get External IP and Update APP_URL

```bash
kubectl get service qr-app

# Update APP_URL with external IP
kubectl set env deployment/qr-app APP_URL=http://YOUR_EXTERNAL_IP
```

</details>

### Open on Big Screen

Navigate to `http://YOUR_EXTERNAL_IP` on your presentation display.

## Using Private Container Registry (GHCR)

If your image is in a private registry like GitHub Container Registry (GHCR):

### With Helm:

```bash
# Create registry secret manually
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USERNAME \
  --docker-password=YOUR_GITHUB_TOKEN

# Deploy with Helm (secret already exists)
helm install qr-pods ./chart \
  --set image.repository=ghcr.io/username/qr-app \
  --set imagePullSecrets.create=false
```

Or let Helm create the secret:

```bash
helm install qr-pods ./chart \
  --set image.repository=ghcr.io/username/qr-app \
  --set imagePullSecrets.username=YOUR_GITHUB_USERNAME \
  --set imagePullSecrets.password=YOUR_GITHUB_TOKEN
```

### With Helmfile:

**Using .env file (easiest):**

```bash
# Configure .env file with your GHCR credentials
cat > .env <<EOF
APP_URL=http://YOUR_EXTERNAL_IP
IMAGE_REPOSITORY=ghcr.io/username/qr-app
IMAGE_TAG=latest
REGISTRY_SERVER=ghcr.io
REGISTRY_USERNAME=your_github_username
REGISTRY_PASSWORD=ghp_your_github_token
EOF

# Deploy
./deploy.sh
```

**Or export environment variables:**

```bash
export APP_URL=http://YOUR_EXTERNAL_IP
export IMAGE_REPOSITORY=ghcr.io/username/qr-app
export REGISTRY_USERNAME=your_github_username
export REGISTRY_PASSWORD=ghp_your_github_token
helmfile sync
```

### GitHub Token Setup:

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token with `read:packages` scope
3. Use the token as `REGISTRY_PASSWORD`

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

# Deploy with Helm
helm install qr-pods ./chart
kubectl port-forward service/qr-pods 5000:80

# OR deploy with manual manifests
kubectl apply -f kubernetes/
kubectl port-forward service/qr-app 5000:80
```

## Configuration

### Helm Values (`chart/values.yaml`)

Key configuration options:

- `app.url` - Public URL for QR code generation
- `app.authToken` - Auth token (leave empty to auto-generate)
- `app.namespace` - Kubernetes namespace for pod creation (default: `default`)
- `image.repository` - Container image repository
- `image.tag` - Container image tag
- `service.type` - Service type (default: `LoadBalancer`)
- `imagePullSecrets.create` - Create registry secret (default: `true`)
- `imagePullSecrets.registry` - Registry server (default: `ghcr.io`)
- `imagePullSecrets.username` - Registry username
- `imagePullSecrets.password` - Registry password/token

Override values with Helm:
```bash
helm install qr-pods ./chart \
  --set app.url=http://1.2.3.4 \
  --set image.repository=myregistry/qr-app \
  --set image.tag=v1.0.0
```

Or with Helmfile environment variables:
```bash
export APP_URL=http://1.2.3.4
export IMAGE_REPOSITORY=myregistry/qr-app
export IMAGE_TAG=v1.0.0
helmfile sync
```

## API Endpoints

- `GET /` - Big screen display page
- `GET /scan?token=X` - Mobile result page (creates pods)
- `GET /api/pod-count` - Returns current pod count
- `GET /api/node-count` - Returns current node count
- `GET /health` - Health check

## Cleanup

```bash
# Delete created demo pods
kubectl delete pods -l app=qr-scaling-demo

# Remove application (Helm)
helm uninstall qr-pods
# OR helmfile destroy

# Remove application (manual manifests)
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
├── chart/                   # Helm chart (recommended)
│   ├── Chart.yaml           # Chart metadata
│   ├── values.yaml          # Default values
│   └── templates/
│       ├── deployment.yaml  # App deployment
│       ├── service.yaml     # LoadBalancer service
│       ├── rbac.yaml        # RBAC configuration
│       ├── secret.yaml      # Auto-generated auth token
│       └── _helpers.tpl     # Template helpers
├── kubernetes/              # Manual manifests (alternative)
│   ├── rbac.yaml            # RBAC (pod + node permissions)
│   ├── secret.yaml          # Auth token
│   ├── app-deployment.yaml  # Deployment manifest
│   └── app-service.yaml     # LoadBalancer service
├── helmfile.yaml            # Helmfile for automation
└── Dockerfile
```

## License

MIT
