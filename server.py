from flask import Flask, jsonify, send_from_directory, request, redirect
from flask_cors import CORS
from read_card import read_card_data, parse_certificate, verify_pin
import os
import logging
import urllib.parse
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
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
@app.route("/cac-utils/")
def index():
    logger.info(f"Serving index for path: {request.path}")
    # Use absolute path to ensure file is found in container
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "viewer.html")

@app.route("/cac-utils")
def redirect_to_slash():
    return redirect("/cac-utils/", code=301)

@app.route("/favicon.png")
@app.route("/cac-utils/favicon.png")
def favicon():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "favicon.png")

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
            cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
            # FIX: x509 module does not have Encoding, it's in serialization
            cert_der = cert.public_bytes(serialization.Encoding.DER)
            
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
        return {
            "success": True,
            "reader": "Cloud Ingress (MTLS)",
            "atr": "N/A (Virtual)",
            "cardInfo": {"protocol": "HTTPS", "type": "MTLS Session (DN Only)"},
            "certs": [{
                "name": "Ingress MTLS Session",
                "subject": {"dn": client_dn},
                "issuer": {"dn": "Unknown (DN Only Mode)"},
                "emails": [],
                "validity": {"notBefore": "", "notAfter": "", "isExpired": False},
                "advanced": {
                    "publicKey": {"algorithm": "Unknown", "size": 0},
                    "thumbprints": {"sha256": "N/A"},
                    "extensions": []
                }
            }],
            "allEmails": []
        }
    
    return None

@app.route("/api/smartcard/read", methods=["GET"])
@app.route("/cac-utils/api/smartcard/read", methods=["GET"])
def read_smartcard():
    logger.info(f"Read request from: {request.remote_addr}")
    header_data = get_data_from_headers()
    if header_data:
        return jsonify(header_data), 200

    try:
        data = read_card_data()
        if not data.get("success", False):
            return jsonify(data), 500
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/smartcard/verify", methods=["POST"])
@app.route("/cac-utils/api/smartcard/verify", methods=["POST"])
def verify_smartcard_pin():
    """Endpoint to verify the card PIN (Local hardware only)."""
    pin = request.json.get("pin")
    if not pin:
        return jsonify({"success": False, "error": "PIN is required"}), 400
    
    logger.info(f"Attempting PIN verification for request from: {request.remote_addr}")
    result = verify_pin(pin)
    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify(result), 401

if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 8000))
    logger.info(f"Starting API on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
