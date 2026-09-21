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
        const newRunning = newCount - newPending - newCreating - newCrashing;

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

        const podsRow = document.getElementById('metric-pods-row');
        if (podsRow) {
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
            totalPriceElement.textContent = formatPrice(data.total_cost || 0);
        }

        renderCostBreakdown(data.price_breakdown || [], hourlyPrice);

        const typeList = document.getElementById('node-type-list');
        if (typeList) {
            const instanceTypes = data.instance_types || {};
            const launchingTypes = data.launching_types || {};
            // Union of every type that's either already running or being
            // launched by Karpenter right now, so a brand-new type shows up
            // immediately even with zero ready nodes of that type yet.
            const allTypes = new Set([...Object.keys(instanceTypes), ...Object.keys(launchingTypes)]);
            const hasTypes = allTypes.size > 0;

            typeList.innerHTML = [...allTypes]
                .sort((a, b) => a.localeCompare(b))
                .map((type) => {
                    const ready = instanceTypes[type] || 0;
                    const launching = launchingTypes[type] || 0;
                    // "(+X)" comes before Y and Y is always the trailing
                    // token, so Y stays anchored at the row's right edge —
                    // launching nodes appearing/disappearing never shifts
                    // the ready count's position.
                    let countHtml = '';
                    if (launching > 0) {
                        countHtml += `<span class="metric-detail-highlight">(+${launching})</span>`;
                    }
                    if (ready > 0) {
                        countHtml += `${launching > 0 ? ' ' : ''}${ready}`;
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

function initCostReset() {
    const btn = document.getElementById('cost-reset-btn');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        if (!confirm('Reset the total spent counter back to €0.00? This cannot be undone.')) {
            return;
        }
        try {
            const response = await fetch('/api/reset-cost', { method: 'POST' });
            if (!response.ok) {
                throw new Error('Failed to reset total spent');
            }
            updateNodeCount();
        } catch (error) {
            console.error('Error resetting total spent:', error);
            alert('Failed to reset total spent. Please try again.');
        }
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
    initCostModal();
    initCostReset();
    startPolling();
    updateIconScale();
});

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    stopPolling();
});
