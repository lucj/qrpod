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
            "pod_count":          {"total": 0, "pending": 0, "crashing": 0},
            "node_count":         {"total": 0, "launching": 0, "instance_types": {}, "launching_types": {}, "hourly_price": 0.0, "price_breakdown": []},
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
            crashing = 0
            for item in items:
                phase = item.get("status", {}).get("phase", "")
                if phase not in ("Running", "Pending"):
                    continue
                total += 1
                if not item.get("spec", {}).get("nodeName"):
                    pending += 1
                    continue
                # A pod stuck in CrashLoopBackOff/OOMKilled still reports
                # phase=Running (kubelet keeps restarting it) — only count it
                # as actually running if every container is presently up.
                container_statuses = item.get("status", {}).get("containerStatuses", [])
                healthy = bool(container_statuses) and all(
                    "running" in cs.get("state", {}) for cs in container_statuses
                )
                if not healthy:
                    crashing += 1
            result = {"total": total, "pending": pending, "crashing": crashing}
        except ApiException as e:
            print(f"Error refreshing pod count: {e}")
            return
        with self._lock:
            self._cache["pod_count"] = result

    def _refresh_node_count(self):
        # Sourced entirely from NodeClaims rather than Node objects. A
        # NodeClaim's own Ready condition (Launched && Registered &&
        # Initialized) is set by Karpenter's controller, while a Node's
        # Ready condition is set by kubelet — two different controllers on
        # two different objects, which used to drift apart for a couple of
        # seconds around the transition (the node count already bumped while
        # the launching count hadn't caught up yet). Reading one object once
        # per poll makes a claim move from launching to ready atomically.
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
                print(f"Error refreshing node count: {e}")
                return

            ready_types = Counter()
            launching_types = Counter()
            all_types = Counter()  # includes unresolved-type claims, for pricing
            for nc in nodeclaims.get("items", []):
                conditions = nc.get("status", {}).get("conditions", [])
                is_ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions)
                itype = nc.get("metadata", {}).get("labels", {}).get("node.kubernetes.io/instance-type")
                all_types[itype or "unknown"] += 1
                if not itype:
                    # Not resolved yet — skip the type breakdown entirely
                    # rather than bucketing it under "unknown".
                    continue
                (ready_types if is_ready else launching_types)[itype] += 1

            price_breakdown = sorted(
                (
                    {
                        "type": itype,
                        "count": count,
                        "unit_price": INSTANCE_PRICES.get(itype, 0.0),
                        "subtotal": INSTANCE_PRICES.get(itype, 0.0) * count,
                    }
                    for itype, count in all_types.items()
                ),
                key=lambda row: row["type"]
            )
            hourly_price = sum(row["subtotal"] for row in price_breakdown)
            result = {
                "total": sum(ready_types.values()),
                "instance_types": dict(ready_types),
                "launching": sum(launching_types.values()),
                "launching_types": dict(launching_types),
                "hourly_price": hourly_price,
                "price_breakdown": price_breakdown,
            }
            with self._lock:
                self._cache["node_count"].update(result)
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
                                        "memory": "64Mi"
                                    },
                                    "limits": {
                                        "cpu": "32m",
                                        "memory": "64Mi"
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
