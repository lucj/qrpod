## Scan Me Maybe: QR Code Driven Pod Scaling With Karpenter

A demo application for Kubernetes that displays a QR code on a big screen. When participants scan it with their phones, it creates 1-10 random pods and shows a visual icon that inflates as pods scale up. Perfect for presentations and demos showcasing Karpenter node autoscaling.

## Features

- **Big Screen Display** - Shows QR code, live visualization, pod count, and node count
- **Mobile Result Page** - Participants see "WOW! You created X Pods" after scanning
- **Real-time Updates** - Metrics update every couple of seconds
- **Visual Scaling** - Icon grows 10% per pod created (max 5x)
- **Token Security** - Basic authentication to prevent abuse

## Architecture

- **Backend:** Python/Flask with Kubernetes Python client
- **Frontend:** HTML/CSS/JavaScript with QRCode.js
- **Two Pages:**
  - `/` - Big screen display with QR code and live metrics
  - `/scan?token=X` - Mobile result page after scanning

## Environment variables

Set the following env vars:

Note: they will be used when deploying the app with Helmfile.

- SCAN_TOKEN: authenticate scans
- DASHBOARD_PASSWORD: access to the dashboard
- SECRET_KEY: used by Flask to signe the session
- QRPOD_REGISTRY_USER: access to the github image
- QRPOD_REGISTRY_PASS: access to the github image
- QRPOD_REGISTRY_EMAIL: access to the github image

## Setup

- Create an SKS cluster with a default nodepool

- Get the kubeconfig and copy it in ./kubeconfig

- Get the ID of the security group

- Copy this ID in the ./infra/nodeclass.yaml specification

```yaml
apiVersion: karpenter.exoscale.com/v1
kind: ExoscaleNodeClass
metadata:
  name: standard
spec:
  imageTemplateSelector:
    version: "1.37.0"
  securityGroupSelectorTerms:
    - id: "REPLACE_WITH_YOUR_SECURITY_GROUP_ID"
```

- create the nodeclass resource

```bash
kubectl apply -f ./infra/nodeclass.yaml
```

- create the Karpenter NodePool

```bash
kubectl apply -f ./infra/nodepool.yaml
```

- Deploy Traefik

```bash
helmfile -f ./infra/helmfile.yaml.gotmpl -l app=traefik apply
```

- Get external IP address

Note: you may need to wait a few tens of seconds before it is available

```bash
EXTERNAL_IP=$(kubectl get svc -n traefik -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')
```

- Deploy cert-manager

Note: you first need to replace the placeholder with your email in *infra/helmfile.yaml.gotmpl*.

```yaml
...
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: REPLACE_WITH_YOUR_EMAIL      <--
    privateKeySecretRef:
      name: letsencrypt-key
    solvers:
      - http01:
          ingress:
            class: traefik
```

```bash
helmfile -f ./infra/helmfile.yaml.gotmpl -l app=cert-manager apply
```

- Deploy the application

```bash
DOMAIN="$EXTERNAL_IP.nip.io"
helmfile -f ./infra/helmfile.yaml.gotmpl -l app=qrpods apply --set app.url="$DOMAIN"
```

## Usage Flow

1. **Display big screen** showing QR code, visualization, and metrics
2. **Participants scan QR code** with their mobile devices
3. **System creates 1-10 random pods** in the cluster
4. **Mobile shows result:** "WOW! You created X Pods" with pod names
5. **Big screen updates live:** Pod count, node count (if Karpenter scales), and icon inflates

## API Endpoints

- `GET /` - Big screen display page
- `GET /scan?token=X` - Mobile result page (creates pods)
- `GET /api/pod-count` - Returns current pod count
- `GET /api/node-count` - Returns current node count
- `GET /health` - Health check

## Cleanup

```bash
# Delete created demo pods
kubectl delete deploy -l app=qrpods

# Remove application (Helm)
helmfile -f ./infra/helmfile.yaml.gotmpl -l app=qrpods destroy
```

## License

MIT
