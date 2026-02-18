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
        self.custom = client.CustomObjectsApi()

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
                                    "memory": "32Mi"
                                },
                                "limits": {
                                    "cpu": "50m",
                                    "memory": "32Mi"
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
            nodes = self.v1.list_node(
                label_selector="karpenter.sh/registered=true"
            )

            not_ready = [
                n for n in nodes.items
                if not any(
                    condition.type == "Ready" and condition.status == "True"
                    for condition in n.status.conditions
                )
            ]

            return {"total": len(nodes.items), "not_ready": len(not_ready)}
        except ApiException as e:
            print(f"Error getting node count: {e}")
            return {"total": 0, "not_ready": 0}


    def get_nodepool_resources(self):
        for version in ("v1", "v1beta1"):
            try:
                nodepools = self.custom.list_cluster_custom_object(
                    group="karpenter.sh",
                    version=version,
                    plural="nodepools"
                )
                capacity = {}
                limits = {}
                for np in nodepools.get('items', []):
                    for key, value in np.get('status', {}).get('resources', {}).items():
                        capacity[key] = value
                    for key, value in np.get('spec', {}).get('limits', {}).items():
                        limits[key] = value
                return {"capacity": capacity, "limits": limits}
            except ApiException:
                continue
            except Exception as e:
                print(f"Error getting nodepool resources: {e}")
                return {"capacity": {}, "limits": {}}
        return {"capacity": {}, "limits": {}}


k8s_manager = KubernetesManager()
