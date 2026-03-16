# CAC-Utils

A collection of lightweight utilities for interacting with Department of Defense (DoD) Common Access Cards (CAC) and Personal Identity Verification (PIV) cards. This project provides a core Python library, a Flask-based API, and a web-based visualization tool.

## Overview

`cac-utils` simplifies the process of reading and parsing data from smart cards. It automatically detects connected readers, selects the appropriate applet (PIV or DoD CAC), and extracts X.509 certificates for Identity, Digital Signature, and Key Management.

## Features

- **Multi-Protocol Support**: Handles both PIV and legacy DoD CAC applets.
- **Certificate Parsing**: Extracts and parses DER-encoded certificates, providing human-readable subject information and validity dates.
- **Flask API**: A ready-to-use backend that exposes card data via a simple JSON endpoint.
- **Diagnostic Viewer**: A modern, single-page web interface (`viewer.html`) to visualize card data in real-time.
- **Containerized**: Includes `Dockerfile` and `docker-compose.yml` for easy deployment.
- **Production Ready**: Helm charts included for Kubernetes deployments with Ingress support.

## Prerequisites

- **Smart Card Reader**: A PC/SC compliant reader.
- **Dependencies**:
  - `pyscard`: For smart card interaction.
  - `cryptography`: For X.509 certificate parsing.
  - `flask`: For the API server.
  - `pcscd`: (Linux only) Ensure the PCSC daemon is running.

## Quick Start

### 1. Local Installation

```bash
# Clone the repository
git clone https://github.com/sft3hy/cac-utils.git
cd cac-utils

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the API Server

```bash
python server.py
```
The server will start at `http://127.0.0.1:8000`.

### 3. View Card Data
Open your browser and navigate to `http://127.0.0.1:8000` to access the **Smart Card Diagnostic Viewer**. Alternatively, you can directly query the API:

```bash
curl http://127.0.0.1:8000/api/smartcard/read
```

## Docker Deployment

The project can be run inside a container, though it requires access to the host's USB devices or PCSC socket.

```bash
docker-compose up --build
```

## Kubernetes (Helm)

A Helm chart is provided in the `helm/` directory.

```bash
helm install cac-utils ./helm -f ./helm/values.yaml
```

The chart supports:
- Ingress with TLS and Client Certificate Authentication (mTLS).
- Custom Nginx configurations for large header support (often needed for certificate forwarding).

## Project Structure

- `read_card.py`: Core logic for card communication using `pyscard` and certificate extraction.
- `server.py`: Flask API server exposing the `/api/smartcard/read` endpoint.
- `viewer.html`: The frontend diagnostic dashboard.
- `probe_cac.py`: CLI utility to list connected readers and probe for supported applet AIDs.
- `nginx.conf`: Nginx configuration for serving the frontend and proxying API requests.

## API Documentation

### Read Smart Card
`GET /api/smartcard/read`

**Response Example:**
```json
{
  "success": true,
  "reader": "SCM Microsystems Inc. SCR3310 [USB Smart Card Reader] 00 00",
  "atr": "3B 7D 96 00 00 80 31 80 65 B0 83 11 00 00 83 00 90 00",
  "cardInfo": {
    "protocol": "T=1",
    "type": "PIV"
  },
  "certs": [
    {
      "name": "PIV Authentication",
      "derLen": 1245,
      "emails": ["john.doe@mail.mil"],
      "subject": {
        "commonName": "DOE.JOHN.123456789",
        "organizationName": "U.S. Government",
        ...
      },
      "validity": {
        "notBefore": "20230101000000Z",
        "notAfter": "20260101235959Z"
      }
    }
  ],
  "allEmails": ["john.doe@mail.mil"]
}
```

## Diagnostic Viewer

The project includes a built-in futuristic web viewer. When running locally or via Docker, simply navigate to the root URL (e.g., `http://localhost:8000`) to see:
- Real-time card status.
- Primary email extraction highlights.
- Detailed certificate subject and validity information.
- Raw ATR (Answer to Reset) hex strings.

## Development

### Python Requirements
Dependencies are managed via `requirements.txt`:
- `pyscard`: High-level Python wrapper for PC/SC.
- `cryptography`: For X.509 parsing and decompressing GZIPped certificates.
- `flask` & `flask-cors`: Web application framework.

### Running Probes
To check for supported applets on a card without running the full API:
```bash
python probe_cac.py
```
