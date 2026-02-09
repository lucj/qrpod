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
    } catch (error) {
        console.error('Error updating node count:', error);
    }
}

function updateIconScale() {
    const icon = document.getElementById('scaling-icon');

    if (icon) {
        // Linear scaling: grows 10% per pod, max 5x
        const scale = Math.min(1 + (currentPodCount * 0.1), 5);
        icon.style.transform = `scale(${scale})`;
    }
}

async function updateMetrics() {
    await Promise.all([
        updatePodCount(),
        updateNodeCount()
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
