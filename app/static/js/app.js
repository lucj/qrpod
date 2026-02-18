let currentPodCount = 0;
let currentNodeCount = 0;
let pollingInterval = null;

function initQRCode() {
    const qrContainer = document.getElementById('qrcode');

    if (qrContainer && typeof QRCode !== 'undefined') {
        new QRCode(qrContainer, {
            text: SCAN_URL,
            width: 300,
            height: 300,
            colorDark: '#667eea',
            colorLight: '#ffffff',
            correctLevel: QRCode.CorrectLevel.H
        });
    }
}

async function updatePodCount() {
    try {
        const response = await fetch('/api/pod-count');

        if (!response.ok) {
            throw new Error('Failed to fetch pod count');
        }

        const data = await response.json();
        const newCount = data.count;
        const newPending = data.pending;

        if (newCount !== currentPodCount) {
            currentPodCount = newCount;

            const podCountElement = document.getElementById('pod-count');
            if (podCountElement) {
                podCountElement.textContent = currentPodCount;

                // Add bump animation
                podCountElement.classList.add('updated');
                setTimeout(() => {
                    podCountElement.classList.remove('updated');
                }, 300);
            }

            updateIconScale();
        }

        const podPendingElement = document.getElementById('pod-pending');
        if (podPendingElement) {
            podPendingElement.textContent = newPending > 0
                ? `${newPending} pending`
                : '';
        }
    } catch (error) {
        console.error('Error updating pod count:', error);
    }
}

async function updateNodeCount() {
    try {
        const response = await fetch('/api/node-count');

        if (!response.ok) {
            throw new Error('Failed to fetch node count');
        }

        const data = await response.json();
        const newCount = data.count;
        const newNotReady = data.not_ready;

        if (newCount !== currentNodeCount) {
            currentNodeCount = newCount;

            const nodeCountElement = document.getElementById('node-count');
            if (nodeCountElement) {
                nodeCountElement.textContent = currentNodeCount;

                // Add bump animation
                nodeCountElement.classList.add('updated');
                setTimeout(() => {
                    nodeCountElement.classList.remove('updated');
                }, 300);
            }

            updateIconScale();
        }

        const nodeNotReadyElement = document.getElementById('node-not-ready');
        if (nodeNotReadyElement) {
            nodeNotReadyElement.textContent = newNotReady > 0
                ? `${newNotReady} not ready`
                : '';
        }
    } catch (error) {
        console.error('Error updating node count:', error);
    }
}

const MAX_PODS = 2000;
const MAX_NODES = 30;
const MIN_SIZE_PX = 80;

function updateIconScale() {
    const icon = document.getElementById('scaling-icon');
    const column = document.querySelector('.visualization-column');

    if (icon && column) {
        const maxSize = Math.min(column.clientWidth, column.clientHeight);
        const podRatio = Math.min(currentPodCount / MAX_PODS, 1);
        const nodeRatio = Math.min(currentNodeCount / MAX_NODES, 1);
        const ratio = Math.max(podRatio, nodeRatio);
        const size = Math.round(MIN_SIZE_PX + (maxSize - MIN_SIZE_PX) * ratio);

        icon.style.width  = `${size}px`;
        icon.style.height = `${size}px`;
    }
}

function formatMemory(value) {
    if (!value) return '—';
    const mi = value.match(/^(\d+(?:\.\d+)?)Mi$/);
    if (mi) {
        const n = parseFloat(mi[1]);
        return n >= 1024 ? `${(n / 1024).toFixed(1)} Gi` : `${Math.round(n)} Mi`;
    }
    return value;
}

async function updateNodepoolResources() {
    try {
        const response = await fetch('/api/nodepool');
        if (!response.ok) throw new Error('Failed to fetch nodepool resources');
        const data = await response.json();

        const capacity = data.capacity || {};
        const limits = data.limits || {};

        const cpuEl = document.getElementById('np-cpu');
        if (cpuEl) cpuEl.textContent = capacity.cpu || '—';

        const memEl = document.getElementById('np-memory');
        if (memEl) memEl.textContent = formatMemory(capacity.memory);

        const podsEl = document.getElementById('np-pods');
        if (podsEl) podsEl.textContent = capacity.pods || '—';

        const limitCpuEl = document.getElementById('np-limit-cpu');
        if (limitCpuEl) limitCpuEl.textContent = limits.cpu || '—';

        const limitMemEl = document.getElementById('np-limit-memory');
        if (limitMemEl) limitMemEl.textContent = formatMemory(limits.memory);
    } catch (error) {
        console.error('Error updating nodepool resources:', error);
    }
}

async function updateMetrics() {
    await Promise.all([
        updatePodCount(),
        updateNodeCount(),
        updateNodepoolResources()
    ]);
}

function startPolling() {
    // Initial update
    updateMetrics();

    // Poll every 3 seconds
    pollingInterval = setInterval(updateMetrics, 3000);
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initQRCode();
    startPolling();
    updateIconScale();
});

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    stopPolling();
});
