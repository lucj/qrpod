import random
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from app.config import config
from app.auth import require_token, require_session
from app.k8s_manager import k8s_manager

app = Flask(__name__,
            template_folder='../templates',
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
    return jsonify({'count': counts['total'], 'pending': counts['pending']})


@app.route('/api/node-count')
def node_count():
    counts = k8s_manager.get_node_count()
    return jsonify({'count': counts['total'], 'not_ready': counts['not_ready'], 'instance_types': counts['instance_types']})


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
    app.run(host='0.0.0.0', port=5000, debug=False)
