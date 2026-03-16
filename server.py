from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from read_card import read_card_data, parse_certificate
import os
import logging
import urllib.parse
from cryptography import x509
from cryptography.hazmat.backends import default_backend

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Enable CORS for the local viewer.html to access this API
CORS(app)

@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors
    logger.error(f"Global Error: {str(e)}")
    return jsonify({"success": False, "error": str(e)}), 500

@app.route("/")
@app.route("/cac-utils")
@app.route("/cac-utils/")
def index():
    logger.info(f"Serving index for path: {request.path}")
    # Use absolute path to ensure file is found in container
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "viewer.html")

@app.route("/health")
@app.route("/cac-utils/health")
def health():
    return jsonify({"status": "healthy"}), 200

def get_data_from_headers():
    """Extracts CAC info from Ingress MTLS headers if available."""
    verify_status = request.headers.get('X-Ssl-Client-Verify') or request.headers.get('Ssl-Client-Verify')
    if verify_status != 'SUCCESS':
        return None

    # Try to get the full cert first
    cert_raw = request.headers.get('X-Ssl-Client-Cert') or request.headers.get('Ssl-Client-Cert')
    if cert_raw:
        try:
            # Nginx $ssl_client_escaped_cert is URL encoded
            cert_pem = urllib.parse.unquote(cert_raw)
            # Ensure it has the PEM boundaries if they were stripped or modified
            if "-----BEGIN CERTIFICATE-----" not in cert_pem:
                # Some ingress controllers might pass the cert in a different format, 
                # but usually it's PEM. We'll try to load it.
                pass
            
            cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
            # We can use the existing parse_certificate but it expects DER bytes. 
            # We can just get the DER back from the object or use our own logic.
            cert_der = cert.public_bytes(x509.Encoding.DER)
            
            parsed = parse_certificate(cert_der, "Ingress MTLS Certificate")
            
            return {
                "success": True,
                "reader": "Cloud Ingress (MTLS)",
                "atr": "N/A (Virtual)",
                "cardInfo": {"protocol": "HTTPS", "type": "MTLS Session"},
                "certs": [parsed],
                "allEmails": parsed.get("emails", [])
            }
        except Exception as e:
            logger.error(f"Failed to parse certificate from header: {e}")

    # Fallback to just the DN if cert parsing failed or was missing
    client_dn = request.headers.get('X-Ssl-Client-Dn') or request.headers.get('Ssl-Client-Subject-Dn')
    if client_dn:
        # Create a minimal fake response based on DN
        return {
            "success": True,
            "reader": "Cloud Ingress (MTLS)",
            "atr": "N/A (Virtual)",
            "cardInfo": {"protocol": "HTTPS", "type": "MTLS Session (DN Only)"},
            "certs": [{
                "name": "Ingress MTLS Session",
                "subject": {"dn": client_dn},
                "emails": [],
                "validity": {}
            }],
            "allEmails": []
        }
    
    return None

@app.route("/api/smartcard/read", methods=["GET"])
@app.route("/cac-utils/api/smartcard/read", methods=["GET"])
def read_smartcard():
    logger.info(f"Read request from: {request.remote_addr} on {request.path}")
    
    # 1. Try to get data from Ingress MTLS headers (Forwarded CAC)
    header_data = get_data_from_headers()
    if header_data:
        logger.info("Successfully extracted CAC info from Ingress headers.")
        return jsonify(header_data), 200

    # 2. Fallback to local hardware reader (Physical CAC)
    try:
        data = read_card_data()
        if not data.get("success", False):
            logger.warning(f"Hardware card read failed: {data.get('error')}")
            return jsonify(data), 500
        return jsonify(data), 200
    except Exception as e:
        logger.exception("Unexpected error in read_smartcard")
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    # Run the local server
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 8000))
    logger.info(f"Starting Smart Card Reader API on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
