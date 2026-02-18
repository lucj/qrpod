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
        self.apps_v1 = client.AppsV1Api()
        self.custom = client.CustomObjectsApi()

    def create_deployment(self, count):
        timestamp = int(time.time())
        deployment_name = f"qr-deployment-{timestamp}-{random.randint(1000, 9999)}"

        deployment_manifest = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": deployment_name,
                "labels": {
                    "app": config.POD_LABEL,
                    "created-by": "qr-scan"
                },
                "annotations": {
                    "created-at": str(timestamp)
                }
            },
            "spec": {
                "replicas": count,
                "selector": {
                    "matchLabels": {
                        "deployment": deployment_name
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": config.POD_LABEL,
                            "deployment": deployment_name,
                            "created-by": "qr-scan"
                        }
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "www",
                                "image": config.POD_IMAGE,
                                "resources": {
                                    "requests": {
                                        "cpu": "32m",
                                        "memory": "16Mi"
                                    },
                                    "limits": {
                                        "cpu": "32m",
                                        "memory": "16Mi"
                                    }
                                }
                            }
                        ],     
                        "affinity": {
                            "nodeAffinity": {
                                "requiredDuringSchedulingIgnoredDuringExecution": {
                                    "nodeSelectorTerms": [
                                        {
                                            "matchExpressions": [
                                                {
                                                    "key": "karpenter.sh/nodepool",
                                                    "operator": "Exists"
                                                }
                                            ]
                                        }
                                    ]
                                }
                            }
                        }
                    }
                }
            }
        }

        try:
            self.apps_v1.create_namespaced_deployment(
                namespace=config.NAMESPACE,
                body=deployment_manifest
            )
            print(f"Created deployment: {deployment_name} with {count} replicas")
            return count
        except ApiException as e:
            print(f"Error creating deployment {deployment_name}: {e}")
            return 0

    def get_pod_count(self):
        try:
            pods = self.v1.list_namespaced_pod(
                namespace=config.NAMESPACE,
                label_selector=f"app={config.POD_LABEL}"
            )

            active = [p for p in pods.items if p.status.phase in ("Running", "Pending")]
            # "pending" = not yet scheduled to a node; ContainerCreating pods already have a node
            pending = [p for p in active if not p.spec.node_name]

            return {"total": len(active), "pending": len(pending)}
        except ApiException as e:
            print(f"Error getting pod count: {e}")
            return {"total": 0, "pending": 0}

    def get_node_count(self):
        try:
            nodes = self.v1.list_node(
                label_selector="karpenter.sh/registered=true"
            )

            ready = [
                n for n in nodes.items
                if any(
                    condition.type == "Ready" and condition.status == "True"
                    for condition in n.status.conditions
                )
            ]
            not_ready = len(nodes.items) - len(ready)

            return {"total": len(ready), "not_ready": not_ready}
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
