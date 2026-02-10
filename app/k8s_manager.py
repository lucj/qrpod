import os
import time
import random
from kubernetes import client, config as k8s_config
from kubernetes.client.rest import ApiException
from app.config import config


class KubernetesManager:
    def __init__(self):
        kubeconfig_path = os.environ.get('KUBECONFIG')
        if kubeconfig_path:
            # Explicit kubeconfig provided (e.g. Docker Compose local dev)
            k8s_config.load_kube_config(config_file=kubeconfig_path)
            print(f"Loaded kubeconfig from {kubeconfig_path}")
        else:
            # Running inside a cluster: use the mounted service account token
            try:
                k8s_config.load_incluster_config()
                print("Loaded in-cluster Kubernetes config")
            except k8s_config.ConfigException:
                raise RuntimeError(
                    "No KUBECONFIG env var set and in-cluster config not available. "
                    "Set KUBECONFIG to the path of your kubeconfig file."
                )

        self.v1 = client.CoreV1Api()

    def create_pods(self, count):
        created_pods = []
        timestamp = int(time.time())

        for i in range(count):
            pod_name = f"qr-pod-{timestamp}-{random.randint(1000, 9999)}"

            pod_manifest = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": pod_name,
                    "labels": {
                        "app": config.POD_LABEL,
                        "created-by": "qr-scan"
                    },
                    "annotations": {
                        "created-at": str(timestamp)
                    }
                },
                "spec": {
                    "containers": [
                        {
                            "name": "www",
                            "image": config.POD_IMAGE,
                            "resources": {
                                "requests": {
                                    "cpu": "50m",
                                    "memory": "64Mi"
                                },
                                "limits": {
                                    "cpu": "50m",
                                    "memory": "64Mi"
                                }
                            }
                        }
                    ],
                    "restartPolicy": "Always"
                }
            }

            try:
                self.v1.create_namespaced_pod(
                    namespace=config.NAMESPACE,
                    body=pod_manifest
                )
                created_pods.append(pod_name)
                print(f"Created pod: {pod_name}")
            except ApiException as e:
                print(f"Error creating pod {pod_name}: {e}")

        return created_pods

    def get_pod_count(self):
        try:
            pods = self.v1.list_namespaced_pod(
                namespace=config.NAMESPACE,
                label_selector=f"app={config.POD_LABEL}"
            )

            pending = [p for p in pods.items if p.status.phase == "Pending"]
            running = [p for p in pods.items if p.status.phase == "Running"]

            return {"total": len(running) + len(pending), "pending": len(pending)}
        except ApiException as e:
            print(f"Error getting pod count: {e}")
            return {"total": 0, "pending": 0}

    def get_node_count(self):
        try:
            nodes = self.v1.list_node()

            ready_nodes = [
                n for n in nodes.items
                if any(
                    condition.type == "Ready" and condition.status == "True"
                    for condition in n.status.conditions
                )
            ]

            return len(ready_nodes)
        except ApiException as e:
            print(f"Error getting node count: {e}")
            return 0


k8s_manager = KubernetesManager()
