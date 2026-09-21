import os
import json
import math
import time
import random
import threading
from collections import Counter
from kubernetes import client, config as k8s_config
from kubernetes.client.rest import ApiException
from config import config

CACHE_TTL = 2  # seconds between Kubernetes API polls

COST_CONFIGMAP_NAME = "qrpods-cost-tracker"
COST_PERSIST_INTERVAL = 30  # seconds between ConfigMap writes for the running total

MEMORY_POD_NAME = "qr-memory"
CPU_POD_NAME = "qr-cpu"

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
            "pod_count":          {"total": 0, "pending": 0, "creating": 0, "crashing": 0, "terminating": 0},
            "node_count":         {"total": 0, "launching": 0, "instance_types": {}, "launching_types": {}, "terminating": 0, "terminating_types": {}, "hourly_price": 0.0, "price_breakdown": []},
            "nodepool_resources": {"capacity": {}, "limits": {}, "available_types": []},
            "total_cost":         self._load_total_cost(),
        }
        self._lock = threading.Lock()
        self._last_cost_tick = time.time()
        self._last_cost_persist = time.time()

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
                self._accumulate_cost()
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
            creating = 0
            crashing = 0
            terminating = 0
            for item in items:
                phase = item.get("status", {}).get("phase", "")
                if phase not in ("Running", "Pending"):
                    continue
                total += 1
                # Mirrors kubectl's own convention: a pod with deletionTimestamp
                # set shows as "Terminating" regardless of its container or
                # scheduling state, taking precedence over every other bucket.
                if item.get("metadata", {}).get("deletionTimestamp"):
                    terminating += 1
                    continue
                if not item.get("spec", {}).get("nodeName"):
                    pending += 1
                    continue
                # A pod stuck in CrashLoopBackOff/OOMKilled still reports
                # phase=Running (kubelet keeps restarting it), so a container
                # not yet "running" isn't automatically a problem — a brand
                # new pod normally has no containerStatuses at all for a
                # moment, then sits in waiting/ContainerCreating (or
                # PodInitializing) while the image pulls and starts. Only
                # count it as crashing once it's past that normal startup.
                container_statuses = item.get("status", {}).get("containerStatuses", [])
                if not container_statuses:
                    creating += 1
                    continue
                is_crashing = False
                is_creating = False
                for cs in container_statuses:
                    state = cs.get("state", {})
                    if "running" in state:
                        continue
                    if state.get("waiting", {}).get("reason") in ("ContainerCreating", "PodInitializing"):
                        is_creating = True
                    else:
                        is_crashing = True
                if is_crashing:
                    crashing += 1
                elif is_creating:
                    creating += 1
            result = {
                "total": total,
                "pending": pending,
                "creating": creating,
                "crashing": crashing,
                "terminating": terminating,
            }
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
            terminating_types = Counter()
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
                # A NodeClaim being consolidated (or otherwise disrupted) away
                # gets deletionTimestamp set and is gracefully drained before
                # it actually disappears — it's still Ready and still counted
                # above during that window, this just flags it as leaving.
                if nc.get("metadata", {}).get("deletionTimestamp"):
                    terminating_types[itype] += 1

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
                "terminating": sum(terminating_types.values()),
                "terminating_types": dict(terminating_types),
                "hourly_price": hourly_price,
                "price_breakdown": price_breakdown,
            }
            with self._lock:
                self._cache["node_count"].update(result)
            return

    # ------------------------------------------------------------------
    # Cumulative cost tracking (persisted across restarts via a ConfigMap)
    # ------------------------------------------------------------------

    def _load_total_cost(self):
        try:
            cm = self.v1.read_namespaced_config_map(COST_CONFIGMAP_NAME, config.NAMESPACE)
            return float((cm.data or {}).get("total_cost", "0"))
        except ApiException as e:
            if e.status != 404:
                print(f"Error loading cost ConfigMap: {e}")
            return 0.0

    def _persist_total_cost(self, total_cost):
        data = {"total_cost": f"{total_cost:.6f}"}
        try:
            self.v1.patch_namespaced_config_map(
                COST_CONFIGMAP_NAME, config.NAMESPACE, {"data": data}
            )
        except ApiException as e:
            if e.status != 404:
                print(f"Error persisting cost ConfigMap: {e}")
                return
            try:
                self.v1.create_namespaced_config_map(
                    config.NAMESPACE,
                    client.V1ConfigMap(
                        metadata=client.V1ObjectMeta(name=COST_CONFIGMAP_NAME),
                        data=data,
                    ),
                )
            except ApiException as e2:
                print(f"Error creating cost ConfigMap: {e2}")

    def _accumulate_cost(self):
        now = time.time()
        elapsed = now - self._last_cost_tick
        self._last_cost_tick = now

        with self._lock:
            hourly_price = self._cache["node_count"]["hourly_price"]
            self._cache["total_cost"] += hourly_price * elapsed / 3600
            current_total = self._cache["total_cost"]

        # Exoscale bills by the second, but the running total only needs to
        # survive a pod restart intact — writing it to the ConfigMap every
        # poll (every CACHE_TTL seconds) would be needless etcd/watch churn,
        # so the in-memory value updates every poll and is only flushed
        # periodically.
        if now - self._last_cost_persist >= COST_PERSIST_INTERVAL:
            self._persist_total_cost(current_total)
            self._last_cost_persist = now

    def reset_total_cost(self):
        with self._lock:
            self._cache["total_cost"] = 0.0
        # Bypass the periodic throttle for an explicit reset — the whole
        # point is that it takes effect immediately, in memory and in the
        # ConfigMap, without waiting up to COST_PERSIST_INTERVAL seconds.
        self._persist_total_cost(0.0)
        self._last_cost_persist = time.time()

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
                available_types = set()
                for np in nodepools.get('items', []):
                    for key, value in np.get('status', {}).get('resources', {}).items():
                        capacity[key] = value
                    for key, value in np.get('spec', {}).get('limits', {}).items():
                        limits[key] = value
                    requirements = np.get('spec', {}).get('template', {}).get('spec', {}).get('requirements', [])
                    for req in requirements:
                        if req.get('key') == 'node.kubernetes.io/instance-type' and req.get('operator') == 'In':
                            available_types.update(req.get('values', []))
                result = {
                    "capacity": capacity,
                    "limits": limits,
                    "available_types": sorted(available_types),
                }
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

    def get_total_cost(self):
        with self._lock:
            return self._cache["total_cost"]

    # ------------------------------------------------------------------

    def get_deployment_count(self):
        try:
            deployments = self.apps_v1.list_namespaced_deployment(
                namespace=config.NAMESPACE,
                label_selector="created-by=qr-scan"
            )
            return len(deployments.items)
        except ApiException as e:
            print(f"Error listing deployments: {e}")
            return 0

    def delete_deployments(self, percent):
        try:
            deployments = self.apps_v1.list_namespaced_deployment(
                namespace=config.NAMESPACE,
                label_selector="created-by=qr-scan"
            )
            items = deployments.items
        except ApiException as e:
            print(f"Error listing deployments for deletion: {e}")
            return 0

        count_to_delete = math.ceil(len(items) * percent / 100)
        deleted = 0
        for dep in items[:count_to_delete]:
            try:
                self.apps_v1.delete_namespaced_deployment(
                    name=dep.metadata.name,
                    namespace=config.NAMESPACE
                )
                deleted += 1
            except ApiException as e:
                print(f"Error deleting deployment {dep.metadata.name}: {e}")
        return deleted

    def _build_deployment_manifest(self, deployment_name, replicas, image, resources, timestamp):
        return {
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
                "replicas": replicas,
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
                                "image": image,
                                "resources": resources
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

    def create_deployment(self, count):
        timestamp = int(time.time())
        deployment_name = f"qr-deployment-{timestamp}-{random.randint(1000, 9999)}"
        resources = {
            "requests": {"cpu": "32m", "memory": "64Mi"},
            "limits": {"cpu": "32m", "memory": "64Mi"}
        }
        manifest = self._build_deployment_manifest(
            deployment_name, count, config.POD_IMAGE, resources, timestamp
        )
        try:
            self.apps_v1.create_namespaced_deployment(
                namespace=config.NAMESPACE,
                body=manifest
            )
            print(f"Created deployment: {deployment_name} with {count} replicas")
            return count
        except ApiException as e:
            print(f"Error creating deployment {deployment_name}: {e}")
            return 0

    def deployment_exists(self, name):
        try:
            self.apps_v1.read_namespaced_deployment(name=name, namespace=config.NAMESPACE)
            return True
        except ApiException as e:
            if e.status != 404:
                print(f"Error checking deployment {name}: {e}")
            return False

    def delete_deployment_by_name(self, name):
        try:
            self.apps_v1.delete_namespaced_deployment(name=name, namespace=config.NAMESPACE)
            return True
        except ApiException as e:
            print(f"Error deleting deployment {name}: {e}")
            return False

    def create_memory_pod(self):
        resources = {
            "requests": {"cpu": "100m", "memory": "20Gi"},
            "limits": {"cpu": "100m", "memory": "20Gi"}
        }
        manifest = self._build_deployment_manifest(
            MEMORY_POD_NAME, 1, "nginx:1.30.5-alpine3.24", resources, int(time.time())
        )
        try:
            self.apps_v1.create_namespaced_deployment(
                namespace=config.NAMESPACE,
                body=manifest
            )
            print(f"Created memory-test deployment: {MEMORY_POD_NAME}")
            return True
        except ApiException as e:
            print(f"Error creating memory-test deployment {MEMORY_POD_NAME}: {e}")
            return False

    def memory_pod_exists(self):
        return self.deployment_exists(MEMORY_POD_NAME)

    def delete_memory_pod(self):
        return self.delete_deployment_by_name(MEMORY_POD_NAME)

    def create_cpu_pod(self):
        resources = {
            "requests": {"cpu": "10", "memory": "64Mi"},
            "limits": {"cpu": "10", "memory": "64Mi"}
        }
        manifest = self._build_deployment_manifest(
            CPU_POD_NAME, 1, "nginx:1.30.5-alpine3.24", resources, int(time.time())
        )
        try:
            self.apps_v1.create_namespaced_deployment(
                namespace=config.NAMESPACE,
                body=manifest
            )
            print(f"Created cpu-test deployment: {CPU_POD_NAME}")
            return True
        except ApiException as e:
            print(f"Error creating cpu-test deployment {CPU_POD_NAME}: {e}")
            return False

    def cpu_pod_exists(self):
        return self.deployment_exists(CPU_POD_NAME)

    def delete_cpu_pod(self):
        return self.delete_deployment_by_name(CPU_POD_NAME)


k8s_manager = KubernetesManager()
