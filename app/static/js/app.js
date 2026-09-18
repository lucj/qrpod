let currentPodCount = 0;
let currentNodeCount = 0;
let currentMemoryCapacityBytes = 0;
let currentMemoryLimitBytes = 0;
let pollingInterval = null;

function initQRCode() {
    const qrContainer = document.getElementById('qrcode');

    if (qrContainer && typeof QRCode !== 'undefined') {
        new QRCode(qrContainer, {
            text: SCAN_URL,
            width: 300,
            height: 300,
            //colorDark: '#667eea',
            //colorDark: '#DA2A1B',
            colorDark: '#64748b',
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

        }

        const podPendingElement = document.getElementById('pod-pending');
        if (podPendingElement) {
            podPendingElement.textContent = newPending > 0
                ? `(${newPending} in Pending)`
                : '';
        }
        return true;
    } catch (error) {
        console.error('Error updating pod count:', error);
        return false;
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
        const newLaunching = data.launching;

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

        }

        const nodeNotReadyElement = document.getElementById('node-not-ready');
        if (nodeNotReadyElement) {
            // "launching" fires the instant Karpenter creates a NodeClaim,
            // well before the instance boots and joins as a Node — show that
            // first so a scale-up reads as instantaneous on screen.
            if (newLaunching > 0) {
                nodeNotReadyElement.textContent = `(🚀 ${newLaunching} launching)`;
            } else if (newNotReady > 0) {
                nodeNotReadyElement.textContent = `(+ ${newNotReady} coming soon)`;
            } else {
                nodeNotReadyElement.textContent = '';
            }
        }

        const typeList = document.getElementById('node-type-list');
        if (typeList) {
            const instanceTypes = data.instance_types || {};
            typeList.innerHTML = Object.entries(instanceTypes)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([type, count]) =>
                    `<div class="node-type-item"><span>${type}</span><span class="node-type-count">${count}</span></div>`
                )
                .join('');
        }
        return true;
    } catch (error) {
        console.error('Error updating node count:', error);
        return false;
    }
}

const MIN_SIZE_PX = 80;

function parseMemoryBytes(value) {
    if (!value) return 0;
    const ki = value.match(/^(\d+(?:\.\d+)?)Ki$/);
    if (ki) return parseFloat(ki[1]) * 1024;
    const mi = value.match(/^(\d+(?:\.\d+)?)Mi$/);
    if (mi) return parseFloat(mi[1]) * 1024 ** 2;
    const gi = value.match(/^(\d+(?:\.\d+)?)Gi$/);
    if (gi) return parseFloat(gi[1]) * 1024 ** 3;
    const ti = value.match(/^(\d+(?:\.\d+)?)Ti$/);
    if (ti) return parseFloat(ti[1]) * 1024 ** 4;
    return parseFloat(value) || 0;
}

function updateIconScale() {
    const icon = document.getElementById('scaling-icon');
    const column = document.querySelector('.visualization-column');

    if (icon && column) {
        const maxSize = Math.min(column.clientWidth, column.clientHeight);
        const ratio = currentMemoryLimitBytes > 0
            ? Math.min(currentMemoryCapacityBytes / currentMemoryLimitBytes, 1)
            : 0;
        const size = Math.round(MIN_SIZE_PX + (maxSize - MIN_SIZE_PX) * ratio);

        icon.style.width  = `${size}px`;
        icon.style.height = `${size}px`;
    }
}

function formatMemory(value) {
    if (!value) return '—';
    const ki = value.match(/^(\d+(?:\.\d+)?)Ki$/);
    if (ki) return `${Math.round(parseFloat(ki[1]) / (1024 * 1024))} Gi`;
    const mi = value.match(/^(\d+(?:\.\d+)?)Mi$/);
    if (mi) {
        const n = parseFloat(mi[1]);
        return n >= 1024 ? `${Math.round(n / 1024)} Gi` : `${Math.round(n)} Mi`;
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
        if (limitCpuEl) limitCpuEl.textContent = limits.cpu ? `/${limits.cpu}` : '';

        const limitMemEl = document.getElementById('np-limit-memory');
        if (limitMemEl) limitMemEl.textContent = limits.memory ? `/${formatMemory(limits.memory)}` : '';

        currentMemoryCapacityBytes = parseMemoryBytes(capacity.memory);
        currentMemoryLimitBytes = parseMemoryBytes(limits.memory);
        updateIconScale();
        return true;
    } catch (error) {
        console.error('Error updating nodepool resources:', error);
        return false;
    }
}

function setConnectionStatus(ok) {
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-label');
    if (dot) dot.classList.toggle('offline', !ok);
    if (label) label.textContent = ok ? 'Live Updates Active' : 'Connection Lost';
}

async function updateMetrics() {
    const results = await Promise.all([
        updatePodCount(),
        updateNodeCount(),
        updateNodepoolResources()
    ]);
    setConnectionStatus(results.every(Boolean));
}

function startPolling() {
    // Initial update
    updateMetrics();

    // Poll every 1.5 seconds
    pollingInterval = setInterval(updateMetrics, 1500);
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
