import time
import random
from kubernetes import client, config as k8s_config
from kubernetes.client.rest import ApiException
from app.config import config


class KubernetesManager:
    def __init__(self):
        try:
            k8s_config.load_incluster_config()
            print("Loaded in-cluster Kubernetes config")
        except k8s_config.ConfigException:
            try:
                k8s_config.load_kube_config()
                print("Loaded local kubeconfig")
            except k8s_config.ConfigException:
                print("Warning: Could not load Kubernetes config")

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
                        "app": "qr-scaling-demo",
                        "created-by": "qr-scan"
                    },
                    "annotations": {
                        "created-at": str(timestamp)
                    }
                },
                "spec": {
                    "containers": [
                        {
                            "name": "nginx",
                            "image": config.POD_IMAGE,
                            "resources": {
                                "requests": {
                                    "cpu": "100m",
                                    "memory": "128Mi"
                                },
                                "limits": {
                                    "cpu": "200m",
                                    "memory": "256Mi"
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
                label_selector="app=qr-scaling-demo"
            )

            running_pods = [
                p for p in pods.items
                if p.status.phase in ["Running", "Pending"]
            ]

            return len(running_pods)
        except ApiException as e:
            print(f"Error getting pod count: {e}")
            return 0

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
