import random
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from config import config
from auth import require_token, require_session
from k8s_manager import k8s_manager

app = Flask(__name__,
            template_folder='./templates',
            static_folder='static',
            static_url_path='/static')

app.secret_key = config.SECRET_KEY


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('token') == config.DASHBOARD_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        error = 'Invalid token'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@require_session
def index():
    scan_url = f"{config.APP_URL}/scan?token={config.SCAN_TOKEN}"
    return render_template('index.html', scan_url=scan_url)


@app.route('/scan')
@require_token
def scan():
    replica_count = random.randint(1, 10)
    created = k8s_manager.create_deployment(replica_count)

    return render_template('scan-result.html',
                         pod_count=created,
                         pod_names=[],
                         token=config.SCAN_TOKEN,
                         namespace=config.NAMESPACE)


@app.route('/api/pod-count')
def pod_count():
    counts = k8s_manager.get_pod_count()
    return jsonify({
        'count': counts['total'],
        'pending': counts['pending'],
        'creating': counts['creating'],
        'crashing': counts['crashing'],
        'terminating': counts['terminating'],
    })


@app.route('/api/node-count')
def node_count():
    counts = k8s_manager.get_node_count()
    return jsonify({
        'count': counts['total'],
        'launching': counts['launching'],
        'instance_types': counts['instance_types'],
        'launching_types': counts['launching_types'],
        'terminating': counts['terminating'],
        'terminating_types': counts['terminating_types'],
        'hourly_price': counts['hourly_price'],
        'price_breakdown': counts['price_breakdown'],
        'total_cost': k8s_manager.get_total_cost(),
    })


@app.route('/api/reset-cost', methods=['POST'])
@require_session
def reset_cost():
    k8s_manager.reset_total_cost()
    return jsonify({'status': 'ok'})


@app.route('/api/deployment-count')
@require_session
def deployment_count():
    return jsonify({'count': k8s_manager.get_deployment_count()})


@app.route('/api/delete-deployments', methods=['POST'])
@require_session
def delete_deployments():
    data = request.get_json(silent=True) or {}
    try:
        percent = int(data.get('percent'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid percent'}), 400
    if percent not in (10, 25, 50, 75, 100):
        return jsonify({'error': 'Invalid percent'}), 400
    deleted = k8s_manager.delete_deployments(percent)
    return jsonify({'status': 'ok', 'deleted': deleted})


@app.route('/api/create-hundred-pods', methods=['POST'])
@require_session
def create_hundred_pods():
    created = k8s_manager.create_deployment(100)
    return jsonify({'status': 'ok' if created else 'error'})


@app.route('/api/create-memory-pod', methods=['POST'])
@require_session
def create_memory_pod():
    created = k8s_manager.create_memory_pod()
    return jsonify({'status': 'ok' if created else 'error'})


@app.route('/api/memory-pod-status')
@require_session
def memory_pod_status():
    return jsonify({'exists': k8s_manager.memory_pod_exists()})


@app.route('/api/delete-memory-pod', methods=['POST'])
@require_session
def delete_memory_pod():
    deleted = k8s_manager.delete_memory_pod()
    return jsonify({'status': 'ok' if deleted else 'error'})


@app.route('/api/create-cpu-pod', methods=['POST'])
@require_session
def create_cpu_pod():
    created = k8s_manager.create_cpu_pod()
    return jsonify({'status': 'ok' if created else 'error'})


@app.route('/api/cpu-pod-status')
@require_session
def cpu_pod_status():
    return jsonify({'exists': k8s_manager.cpu_pod_exists()})


@app.route('/api/delete-cpu-pod', methods=['POST'])
@require_session
def delete_cpu_pod():
    deleted = k8s_manager.delete_cpu_pod()
    return jsonify({'status': 'ok' if deleted else 'error'})


@app.route('/api/nodepool')
def nodepool():
    resources = k8s_manager.get_nodepool_resources()
    return jsonify(resources)


@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200


if __name__ == '__main__':
    print(f"Starting QR Pods application...")
    print(f"Scan Token: {config.SCAN_TOKEN}")
    print(f"Namespace: {config.NAMESPACE}")
    print(f"App URL: {config.APP_URL}")
    app.run(host='0.0.0.0', port=config.APP_PORT, debug=False)
