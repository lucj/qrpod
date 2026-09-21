let currentPodCount = 0;
let currentNodeCount = 0;
let currentMemoryCapacityBytes = 0;
let currentMemoryLimitBytes = 0;
let pollingInterval = null;

const HOURS_PER_DAY = 24;
// Standard cloud-billing approximation (365.25 days/year * 24h / 12 months).
const HOURS_PER_MONTH = 730;

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
        const newCreating = data.creating;
        const newCrashing = data.crashing;
        const newTerminating = data.terminating;
        const newRunning = newCount - newPending - newCreating - newCrashing - newTerminating;

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
            podPendingElement.textContent = newPending;
        }

        const podPendingRow = document.getElementById('pod-pending-row');
        if (podPendingRow) {
            podPendingRow.classList.toggle('hidden', newPending === 0);
        }

        const podCreatingElement = document.getElementById('pod-creating');
        if (podCreatingElement) {
            podCreatingElement.textContent = newCreating;
        }

        const podCreatingRow = document.getElementById('pod-creating-row');
        if (podCreatingRow) {
            podCreatingRow.classList.toggle('hidden', newCreating === 0);
        }

        const podRunningElement = document.getElementById('pod-running');
        if (podRunningElement) {
            podRunningElement.textContent = newRunning;
        }

        const podCrashingElement = document.getElementById('pod-crashing');
        if (podCrashingElement) {
            podCrashingElement.textContent = newCrashing;
        }

        const podCrashingRow = document.getElementById('pod-crashing-row');
        if (podCrashingRow) {
            podCrashingRow.classList.toggle('hidden', newCrashing === 0);
        }

        const podTerminatingElement = document.getElementById('pod-terminating');
        if (podTerminatingElement) {
            podTerminatingElement.textContent = newTerminating;
        }

        const podTerminatingRow = document.getElementById('pod-terminating-row');
        if (podTerminatingRow) {
            podTerminatingRow.classList.toggle('hidden', newTerminating === 0);
        }

        const podsRow = document.getElementById('metric-pods-row');
        if (podsRow) {
            // Only collapse when there are no pods at all. Running is kept
            // visible even when it equals the total — toggling the whole
            // right column on and off every time pods finish starting up
            // was a more distracting flicker than the minor redundancy of
            // always showing "Running".
            podsRow.classList.toggle('no-details', newCount === 0);
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

        const hourlyPrice = data.hourly_price || 0;
        const dailyPrice = hourlyPrice * HOURS_PER_DAY;
        const monthlyPrice = hourlyPrice * HOURS_PER_MONTH;

        const hourlyPriceElement = document.getElementById('hourly-price');
        if (hourlyPriceElement) {
            hourlyPriceElement.textContent = formatPrice(hourlyPrice);
        }

        const dailyPriceElement = document.getElementById('daily-price');
        if (dailyPriceElement) {
            dailyPriceElement.textContent = formatPrice(dailyPrice);
        }

        const monthlyPriceElement = document.getElementById('monthly-price');
        if (monthlyPriceElement) {
            monthlyPriceElement.textContent = formatPrice(monthlyPrice);
        }

        const totalPriceElement = document.getElementById('total-price');
        if (totalPriceElement) {
            totalPriceElement.textContent = `€${(data.total_cost || 0).toFixed(2)}`;
        }

        renderCostBreakdown(data.price_breakdown || [], hourlyPrice);

        const typeList = document.getElementById('node-type-list');
        if (typeList) {
            const instanceTypes = data.instance_types || {};
            const launchingTypes = data.launching_types || {};
            const terminatingTypes = data.terminating_types || {};
            // Union of every type that's running, launching, or being
            // consolidated away right now, so a brand-new type shows up
            // immediately even with zero ready nodes of that type yet.
            const allTypes = new Set([
                ...Object.keys(instanceTypes),
                ...Object.keys(launchingTypes),
                ...Object.keys(terminatingTypes),
            ]);
            const hasTypes = allTypes.size > 0;

            typeList.innerHTML = [...allTypes]
                .sort((a, b) => a.localeCompare(b))
                .map((type) => {
                    const ready = instanceTypes[type] || 0;
                    const launching = launchingTypes[type] || 0;
                    const terminating = terminatingTypes[type] || 0;
                    // Both "(+X)" and "(-Z)" come before Y, and Y is always
                    // the trailing token, so Y stays anchored at the row's
                    // right edge — nodes starting or finishing launching/
                    // terminating never shifts the ready count's position.
                    let countHtml = '';
                    if (launching > 0) {
                        countHtml += `<span class="metric-detail-highlight">(+${launching})</span>`;
                    }
                    if (terminating > 0) {
                        countHtml += `${launching > 0 ? ' ' : ''}<span class="metric-detail-fade">(-${terminating})</span>`;
                    }
                    if (ready > 0) {
                        countHtml += `${(launching > 0 || terminating > 0) ? ' ' : ''}${ready}`;
                    }
                    return `<div class="metric-detail-item"><span>${type}</span><span class="metric-detail-count">${countHtml}</span></div>`;
                })
                .join('');

            const nodesRow = document.getElementById('metric-nodes-row');
            if (nodesRow) {
                nodesRow.classList.toggle('no-details', !hasTypes);
            }
        }
        return true;
    } catch (error) {
        console.error('Error updating node count:', error);
        return false;
    }
}

function formatPrice(value) {
    return `€${value.toFixed(value < 1 ? 3 : 2)}`;
}

function renderCostBreakdown(breakdown, hourlyTotal) {
    const table = document.getElementById('cost-invoice-table');
    if (!table) return;

    if (!breakdown.length) {
        table.innerHTML = '<div class="invoice-empty">No active nodes</div>';
        return;
    }

    const rows = breakdown.map((row) => `
        <div class="invoice-cell invoice-cell-left">${row.type}</div>
        <div class="invoice-cell">${row.count}</div>
        <div class="invoice-cell">${formatPrice(row.unit_price)}</div>
        <div class="invoice-cell">${formatPrice(row.subtotal)}</div>
        <div class="invoice-cell">${formatPrice(row.subtotal * HOURS_PER_DAY)}</div>
        <div class="invoice-cell">${formatPrice(row.subtotal * HOURS_PER_MONTH)}</div>
    `).join('');

    const dailyTotal = hourlyTotal * HOURS_PER_DAY;
    const monthlyTotal = hourlyTotal * HOURS_PER_MONTH;

    table.innerHTML = `
        <div class="invoice-header invoice-cell invoice-cell-left">Type</div>
        <div class="invoice-header invoice-cell">Qty</div>
        <div class="invoice-header invoice-cell">Unit /hr</div>
        <div class="invoice-header invoice-cell">Subtotal /hr</div>
        <div class="invoice-header invoice-cell">Subtotal /day</div>
        <div class="invoice-header invoice-cell">Subtotal /month</div>
        ${rows}
        <div class="invoice-total-label">Total</div>
        <div class="invoice-total-value">${formatPrice(hourlyTotal)}</div>
        <div class="invoice-total-value">${formatPrice(dailyTotal)}</div>
        <div class="invoice-total-value">${formatPrice(monthlyTotal)}</div>
    `;
}

function initCostModal() {
    const btn = document.getElementById('cost-info-btn');
    const overlay = document.getElementById('cost-modal-overlay');
    const closeBtn = document.getElementById('cost-modal-close');
    if (!btn || !overlay || !closeBtn) return;

    const open = () => overlay.classList.add('open');
    const close = () => overlay.classList.remove('open');

    btn.addEventListener('click', open);
    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') close();
    });
}

// Shared wiring for the "explain the action, single confirm button, POST on
// click" modal pattern (reset cost). Each caller just supplies its own
// element ids, endpoint, and what to refresh afterward.
function initConfirmActionModal({ triggerId, overlayId, closeId, confirmId, endpoint, refresh, errorMessage }) {
    const btn = document.getElementById(triggerId);
    const overlay = document.getElementById(overlayId);
    const closeBtn = document.getElementById(closeId);
    const confirmBtn = document.getElementById(confirmId);
    if (!btn || !overlay || !closeBtn || !confirmBtn) return;

    const open = () => overlay.classList.add('open');
    const close = () => overlay.classList.remove('open');

    btn.addEventListener('click', open);
    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') close();
    });

    confirmBtn.addEventListener('click', async () => {
        try {
            const response = await fetch(endpoint, { method: 'POST' });
            if (!response.ok) {
                throw new Error(errorMessage);
            }
            close();
            refresh();
        } catch (error) {
            console.error(errorMessage, error);
            alert(`${errorMessage}. Please try again.`);
        }
    });
}

function initCostReset() {
    initConfirmActionModal({
        triggerId: 'cost-reset-btn',
        overlayId: 'reset-cost-modal-overlay',
        closeId: 'reset-cost-modal-close',
        confirmId: 'reset-cost-confirm-btn',
        endpoint: '/api/reset-cost',
        refresh: updateNodeCount,
        errorMessage: 'Failed to reset total spent',
    });
}

function initDeleteModal() {
    const btn = document.getElementById('delete-pods-btn');
    const overlay = document.getElementById('delete-modal-overlay');
    const closeBtn = document.getElementById('delete-modal-close');
    const select = document.getElementById('delete-percent-select');
    const countEl = document.getElementById('delete-deployment-count');
    const previewEl = document.getElementById('delete-preview-count');
    const confirmBtn = document.getElementById('delete-confirm-btn');
    if (!btn || !overlay || !closeBtn || !select || !countEl || !previewEl || !confirmBtn) return;

    let currentCount = 0;

    function updatePreview() {
        const percent = parseInt(select.value, 10);
        const toDelete = Math.ceil(currentCount * percent / 100);
        previewEl.textContent = currentCount > 0
            ? `≈ ${toDelete} deployment${toDelete === 1 ? '' : 's'} will be deleted`
            : '';
    }

    async function open() {
        overlay.classList.add('open');
        countEl.textContent = '…';
        try {
            const response = await fetch('/api/deployment-count');
            if (!response.ok) throw new Error('Failed to fetch deployment count');
            const data = await response.json();
            currentCount = data.count || 0;
            countEl.textContent = currentCount;
            updatePreview();
        } catch (error) {
            countEl.textContent = '—';
            console.error('Error fetching deployment count:', error);
        }
    }

    const close = () => overlay.classList.remove('open');

    btn.addEventListener('click', open);
    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') close();
    });
    select.addEventListener('change', updatePreview);

    confirmBtn.addEventListener('click', async () => {
        const percent = parseInt(select.value, 10);
        try {
            const response = await fetch('/api/delete-deployments', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ percent }),
            });
            if (!response.ok) {
                throw new Error('Failed to delete deployments');
            }
            close();
            updateMetrics();
        } catch (error) {
            console.error('Error deleting deployments:', error);
            alert('Failed to delete deployments. Please try again.');
        }
    });
}

function initNodesModal() {
    const btn = document.getElementById('nodes-info-btn');
    const overlay = document.getElementById('nodes-modal-overlay');
    const closeBtn = document.getElementById('nodes-modal-close');
    if (!btn || !overlay || !closeBtn) return;

    const open = () => overlay.classList.add('open');
    const close = () => overlay.classList.remove('open');

    btn.addEventListener('click', open);
    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') close();
    });
}

// Shared wiring for the "single named pod, toggle between create and
// delete" modal pattern (memory/cpu test pods). Only the Create button and
// spec list show when the deployment doesn't exist yet; only the Delete
// button and delete notice show once it does.
function initTogglePodModal({ triggerId, overlayId, closeId, createBtnId, deleteBtnId, createInfoId, deleteInfoId, statusEndpoint, createEndpoint, deleteEndpoint, refresh, errorMessage }) {
    const btn = document.getElementById(triggerId);
    const overlay = document.getElementById(overlayId);
    const closeBtn = document.getElementById(closeId);
    const createBtn = document.getElementById(createBtnId);
    const deleteBtn = document.getElementById(deleteBtnId);
    const createInfo = document.getElementById(createInfoId);
    const deleteInfo = document.getElementById(deleteInfoId);
    if (!btn || !overlay || !closeBtn || !createBtn || !deleteBtn || !createInfo || !deleteInfo) return;

    const setState = (exists) => {
        createInfo.classList.toggle('hidden', exists);
        deleteInfo.classList.toggle('hidden', !exists);
        createBtn.classList.toggle('hidden', exists);
        deleteBtn.classList.toggle('hidden', !exists);
    };

    const refreshStatus = async () => {
        try {
            const response = await fetch(statusEndpoint);
            if (!response.ok) throw new Error(errorMessage);
            const data = await response.json();
            setState(!!data.exists);
        } catch (error) {
            console.error(errorMessage, error);
        }
    };

    const open = () => {
        overlay.classList.add('open');
        refreshStatus();
    };
    const close = () => overlay.classList.remove('open');

    btn.addEventListener('click', open);
    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') close();
    });

    const runAction = async (endpoint) => {
        try {
            const response = await fetch(endpoint, { method: 'POST' });
            if (!response.ok) throw new Error(errorMessage);
            close();
            refresh();
        } catch (error) {
            console.error(errorMessage, error);
            alert(`${errorMessage}. Please try again.`);
        }
    };

    createBtn.addEventListener('click', () => runAction(createEndpoint));
    deleteBtn.addEventListener('click', () => runAction(deleteEndpoint));
}

function initMemoryPodModal() {
    initTogglePodModal({
        triggerId: 'memory-pod-btn',
        overlayId: 'memory-pod-modal-overlay',
        closeId: 'memory-pod-modal-close',
        createBtnId: 'memory-pod-create-btn',
        deleteBtnId: 'memory-pod-delete-btn',
        createInfoId: 'memory-pod-create-info',
        deleteInfoId: 'memory-pod-delete-info',
        statusEndpoint: '/api/memory-pod-status',
        createEndpoint: '/api/create-memory-pod',
        deleteEndpoint: '/api/delete-memory-pod',
        refresh: updateMetrics,
        errorMessage: 'Failed to update memory-heavy pod',
    });
}

function initCpuPodModal() {
    initTogglePodModal({
        triggerId: 'cpu-pod-btn',
        overlayId: 'cpu-pod-modal-overlay',
        closeId: 'cpu-pod-modal-close',
        createBtnId: 'cpu-pod-create-btn',
        deleteBtnId: 'cpu-pod-delete-btn',
        createInfoId: 'cpu-pod-create-info',
        deleteInfoId: 'cpu-pod-delete-info',
        statusEndpoint: '/api/cpu-pod-status',
        createEndpoint: '/api/create-cpu-pod',
        deleteEndpoint: '/api/delete-cpu-pod',
        refresh: updateMetrics,
        errorMessage: 'Failed to update CPU-heavy pod',
    });
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
    const tooltip = document.querySelector('.capacity-tooltip');

    if (icon && column) {
        // The tooltip shares the column (stacked above the icon via
        // flex-direction: column), so its height + the gap between them
        // must be subtracted before sizing the icon, or a large icon would
        // push the tooltip out of view / overflow the column.
        const columnStyle = getComputedStyle(column);
        const gap = parseFloat(columnStyle.rowGap || columnStyle.gap || '0') || 0;
        const tooltipSpace = tooltip ? tooltip.offsetHeight + gap : 0;
        const availableHeight = column.clientHeight - tooltipSpace;
        const maxSize = Math.min(column.clientWidth, availableHeight);
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

        const limitCpuEl = document.getElementById('np-limit-cpu');
        if (limitCpuEl) limitCpuEl.textContent = limits.cpu ? `/${limits.cpu}` : '';

        const limitMemEl = document.getElementById('np-limit-memory');
        if (limitMemEl) limitMemEl.textContent = limits.memory ? `/${formatMemory(limits.memory)}` : '';

        currentMemoryCapacityBytes = parseMemoryBytes(capacity.memory);
        currentMemoryLimitBytes = parseMemoryBytes(limits.memory);
        updateIconScale();

        const typesEl = document.getElementById('nodes-available-types');
        if (typesEl) {
            const availableTypes = data.available_types || [];
            typesEl.innerHTML = availableTypes
                .map((type) => `<span class="type-chip">${type}</span>`)
                .join('');
        }
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
    initCostModal();
    initCostReset();
    initDeleteModal();
    initNodesModal();
    initMemoryPodModal();
    initCpuPodModal();
    startPolling();
    updateIconScale();
});

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    stopPolling();
});
