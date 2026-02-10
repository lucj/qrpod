import random
from flask import Flask, render_template, jsonify, request, redirect, url_for
from app.config import config
from app.auth import require_token
from app.k8s_manager import k8s_manager

app = Flask(__name__,
            template_folder='../templates',
            static_folder='static',
            static_url_path='/static')


@app.route('/')
def index():
    scan_url = f"{config.APP_URL}/scan?token={config.AUTH_TOKEN}"
    return render_template('index.html',
                         scan_url=scan_url,
                         auth_token=config.AUTH_TOKEN)


@app.route('/scan')
@require_token
def scan():
    pod_count = random.randint(1, 10)

    created_pods = k8s_manager.create_pods(pod_count)

    return render_template('scan-result.html',
                         pod_count=len(created_pods),
                         pod_names=created_pods,
                         token=config.AUTH_TOKEN,
                         namespace=config.NAMESPACE)


@app.route('/api/pod-count')
def pod_count():
    counts = k8s_manager.get_pod_count()
    return jsonify({'count': counts['total'], 'pending': counts['pending']})


@app.route('/api/node-count')
def node_count():
    count = k8s_manager.get_node_count()
    return jsonify({'count': count})


@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200


if __name__ == '__main__':
    print(f"Starting QR Pods application...")
    print(f"Auth Token: {config.AUTH_TOKEN}")
    print(f"Namespace: {config.NAMESPACE}")
    print(f"App URL: {config.APP_URL}")
    app.run(host='0.0.0.0', port=5000, debug=False)
