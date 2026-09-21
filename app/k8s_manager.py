import os
import json
import time
import random
import threading
from collections import Counter
from kubernetes import client, config as k8s_config
from kubernetes.client.rest import ApiException
from config import config

CACHE_TTL = 2  # seconds between Kubernetes API polls

PRICES_PATH = os.path.join(os.path.dirname(__file__), "assets", "prices.json")
with open(PRICES_PATH) as f:
    INSTANCE_PRICES = {itype: float(price) for itype, price in json.load(f).items()}


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

        self._cache = {
            "pod_count":          {"total": 0, "pending": 0},
            "node_count":         {"total": 0, "not_ready": 0, "launching": 0, "instance_types": {}, "hourly_price": 0.0},
            "nodepool_resources": {"capacity": {}, "limits": {}},
        }
        self._lock = threading.Lock()

        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Background polling loop
    # ------------------------------------------------------------------

    def _poll_loop(self):
        while True:
            try:
                self._refresh_pod_count()
                self._refresh_node_count()
                self._refresh_launching_count()
                self._refresh_nodepool_resources()
            except Exception as e:
                print(f"Unexpected error in poll loop: {e}")
            time.sleep(CACHE_TTL)

    def _refresh_pod_count(self):
        try:
            raw = self.v1.list_namespaced_pod(
                namespace=config.NAMESPACE,
                label_selector=f"app={config.POD_LABEL}",
                _preload_content=False
            )
            items = json.loads(raw.data).get("items", [])
            total = 0
            pending = 0
            for item in items:
                phase = item.get("status", {}).get("phase", "")
                if phase in ("Running", "Pending"):
                    total += 1
                    if not item.get("spec", {}).get("nodeName"):
                        pending += 1
            result = {"total": total, "pending": pending}
        except ApiException as e:
            print(f"Error refreshing pod count: {e}")
            return
        with self._lock:
            self._cache["pod_count"] = result

    def _refresh_node_count(self):
        try:
            # "karpenter.sh/nodepool" is set by kubelet at boot time (from the
            # NodePool's user-data), so it's visible as soon as the Node object
            # registers with the API server. "karpenter.sh/registered=true" is
            # only added later, once Karpenter's own controller reconciles the
            # node — waiting for that adds a very noticeable, avoidable delay.
            raw = self.v1.list_node(
                label_selector="karpenter.sh/nodepool",
                _preload_content=False
            )
            items = json.loads(raw.data).get("items", [])
            total = len(items)
            ready = 0
            instance_types = Counter()
            for item in items:
                conditions = item.get("status", {}).get("conditions", [])
                if any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions):
                    ready += 1
                itype = item.get("metadata", {}).get("labels", {}).get(
                    "node.kubernetes.io/instance-type", "unknown"
                )
                instance_types[itype] += 1
            hourly_price = sum(
                INSTANCE_PRICES.get(itype, 0.0) * count
                for itype, count in instance_types.items()
            )
            result = {
                "total": ready,
                "not_ready": total - ready,
                "instance_types": dict(instance_types),
                "hourly_price": hourly_price,
            }
        except ApiException as e:
            print(f"Error refreshing node count: {e}")
            return
        with self._lock:
            self._cache["node_count"].update(result)

    def _refresh_launching_count(self):
        # NodeClaims appear the instant Karpenter decides to scale up — well
        # before the underlying instance boots and joins as a Node — so this
        # is the earliest possible signal that a scale-up was triggered.
        for version in ("v1", "v1beta1"):
            try:
                nodeclaims = self.custom.list_cluster_custom_object(
                    group="karpenter.sh",
                    version=version,
                    plural="nodeclaims"
                )
            except ApiException:
                continue
            except Exception as e:
                print(f"Error refreshing launching count: {e}")
                return
            launching = 0
            for nc in nodeclaims.get("items", []):
                conditions = nc.get("status", {}).get("conditions", [])
                if not any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions):
                    launching += 1
            with self._lock:
                self._cache["node_count"]["launching"] = launching
            return

    def _refresh_nodepool_resources(self):
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
                result = {"capacity": capacity, "limits": limits}
            except ApiException:
                continue
            except Exception as e:
                print(f"Error refreshing nodepool resources: {e}")
                return
            with self._lock:
                self._cache["nodepool_resources"] = result
            return

    # ------------------------------------------------------------------
    # Public API — return cached data instantly
    # ------------------------------------------------------------------

    def get_pod_count(self):
        with self._lock:
            return dict(self._cache["pod_count"])

    def get_node_count(self):
        with self._lock:
            return dict(self._cache["node_count"])

    def get_nodepool_resources(self):
        with self._lock:
            return dict(self._cache["nodepool_resources"])

    # ------------------------------------------------------------------

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


k8s_manager = KubernetesManager()
