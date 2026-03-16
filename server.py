from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from read_card import read_card_data
import os
import logging

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

@app.route("/api/smartcard/read", methods=["GET"])
@app.route("/cac-utils/api/smartcard/read", methods=["GET"])
def read_smartcard():
    logger.info(f"Read request from: {request.remote_addr} on {request.path}")
    logger.info(f"Headers: {dict(request.headers)}")
    try:
        data = read_card_data()
        if not data.get("success", False):
            logger.warning(f"Card read failed: {data.get('error')}")
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
