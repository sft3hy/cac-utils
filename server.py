from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from read_card import read_card_data

import os

app = Flask(__name__)
# Enable CORS for the local viewer.html to access this API
CORS(app)


@app.route("/")
def index():
    return send_from_directory(".", "viewer.html")


@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200


@app.route("/api/smartcard/read", methods=["GET"])
def read_smartcard():
    try:
        data = read_card_data()
        if not data.get("success", False):
            return jsonify(data), 500
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    # Run the local server
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", 8000))
    print(f"Starting Smart Card Reader API on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
