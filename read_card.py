import sys
from smartcard.System import readers
from smartcard.util import toHexString
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
import datetime

# PIV AID: A0 00 00 03 08 00 00 10 00
PIV_AID = [0xA0, 0x00, 0x00, 0x03, 0x08, 0x00, 0x00, 0x10, 0x00]
SELECT_PIV = [0x00, 0xA4, 0x04, 0x00, len(PIV_AID)] + PIV_AID

PIV_CERTS = [
    {"name": "PIV Authentication", "tag": [0x5C, 0x03, 0x5F, 0xC1, 0x05]},
    {"name": "Digital Signature", "tag": [0x5C, 0x03, 0x5F, 0xC1, 0x0A]},
    {"name": "Key Management", "tag": [0x5C, 0x03, 0x5F, 0xC1, 0x0B]},
    {"name": "Card Authentication", "tag": [0x5C, 0x03, 0x5F, 0xC1, 0x01]},
]

def transmit_apdu(connection, apdu):
    response, sw1, sw2 = connection.transmit(apdu)
    # Check for chained response (61XX or 6CXX)
    full_response = list(response)
    while sw1 == 0x61 or sw1 == 0x6C:
        get_response_apdu = [0x00, 0xC0, 0x00, 0x00, sw2 if sw1 == 0x6C else 0x00]
        response, sw1, sw2 = connection.transmit(get_response_apdu)
        full_response.extend(response)
    return full_response, sw1, sw2

def extract_cert_from_piv(piv_data):
    try:
        i = 0
        if piv_data[i] == 0x53: # top level PIV wrapper
            i += 1
            length = piv_data[i]
            if length & 0x80:
                num_bytes = length & 0x7F
                i += 1 + num_bytes
            else:
                i += 1
            while i < len(piv_data):
                tag = piv_data[i]
                i += 1
                length = piv_data[i]
                if length & 0x80:
                    num_bytes = length & 0x7F
                    length = 0
                    for _ in range(num_bytes):
                        i += 1
                        length = (length << 8) | piv_data[i]
                i += 1
                if tag == 0x70:
                    return bytes(piv_data[i:i+length])
                i += length
    except Exception as e:
        print(f"Error parsing TLV: {e}")
    return None

def parse_certificate(cert_bytes, name):
    result = {
        "name": name,
        "derLen": len(cert_bytes),
        "emails": [],
        "subject": {},
        "issuer": {},
        "validity": {},
        "advanced": {
            "publicKey": {},
            "thumbprints": {},
            "extensions": []
        }
    }
    try:
        if len(cert_bytes) > 2 and cert_bytes[0] == 0x1f and cert_bytes[1] == 0x8b:
            import gzip
            try:
                cert_bytes = gzip.decompress(cert_bytes)
            except Exception:
                return result
                
        cert = x509.load_der_x509_certificate(cert_bytes, default_backend())
        
        # Basic Info
        for attr in cert.subject:
            result["subject"][attr.oid._name] = attr.value
        for attr in cert.issuer:
            result["issuer"][attr.oid._name] = attr.value
            
        result["validity"] = {
            "notBefore": cert.not_valid_before_utc.strftime('%Y%m%d%H%M%SZ'),
            "notAfter": cert.not_valid_after_utc.strftime('%Y%m%d%H%M%SZ'),
            "isExpired": cert.not_valid_after_utc < datetime.datetime.now(datetime.timezone.utc)
        }

        # Thumbprints
        result["advanced"]["thumbprints"] = {
            "sha1": cert.fingerprint(hashes.SHA1()).hex().upper(),
            "sha256": cert.fingerprint(hashes.SHA256()).hex().upper()
        }

        # Public Key Info
        pub = cert.public_key()
        from cryptography.hazmat.primitives.asymmetric import rsa, ec
        if isinstance(pub, rsa.RSAPublicKey):
            result["advanced"]["publicKey"] = {
                "algorithm": "RSA",
                "size": pub.key_size,
                "modulus": hex(pub.public_numbers().n),
                "exponent": pub.public_numbers().e
            }
        elif isinstance(pub, ec.EllipticCurvePublicKey):
            result["advanced"]["publicKey"] = {
                "algorithm": "EC",
                "size": pub.key_size,
                "curve": pub.curve.name
            }

        # Extensions & Emails
        for ext in cert.extensions:
            # SAN special handling for emails
            if ext.oid == x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME:
                for name_obj in ext.value:
                    if isinstance(name_obj, x509.RFC822Name):
                        result["emails"].append(name_obj.value)
            
            result["advanced"]["extensions"].append({
                "oid": ext.oid.dotted_string,
                "name": ext.oid._name,
                "critical": ext.critical
            })
            
    except Exception as e:
        print(f"Failed to parse X.509 certificate: {e}")
        
    return result

def verify_pin(pin):
    """
    Attempts to verify a PIN against the card.
    Note: PIV uses 00 20 00 80 for PIN verification.
    """
    r = readers()
    if not r: return {"success": False, "error": "No reader"}
    
    try:
        connection = r[0].createConnection()
        connection.connect()
        # SELECT PIV first
        transmit_apdu(connection, SELECT_PIV)
        
        # Construct PIN APDU: 00 20 00 80 08 [PIN padded with FF]
        # PIN is usually 6-8 digits
        pin_bytes = [ord(c) for c in pin]
        if len(pin_bytes) < 8:
            pin_bytes += [0xFF] * (8 - len(pin_bytes))
        
        verify_apdu = [0x00, 0x20, 0x00, 0x80, 0x08] + pin_bytes
        response, sw1, sw2 = connection.transmit(verify_apdu)
        
        connection.disconnect()
        
        if sw1 == 0x90 and sw2 == 0x00:
            return {"success": True, "message": "PIN Verified Successfully"}
        elif sw1 == 0x63:
            attempts = sw2 & 0x0F
            return {"success": False, "error": f"Invalid PIN. {attempts} attempts remaining."}
        else:
            return {"success": False, "error": f"Verification failed. SW: {sw1:02X} {sw2:02X}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

def read_card_data():
    result = {
        "success": False,
        "error": None,
        "reader": None,
        "atr": None,
        "cardInfo": {"protocol": "Unknown", "type": "Unknown"},
        "certs": [],
        "allEmails": []
    }

    r = readers()
    if not r:
        result["error"] = "No smart card readers found."
        return result

    reader = r[0]
    result["reader"] = str(reader)
    
    try:
        connection = reader.createConnection()
        connection.connect()
    except Exception as e:
        result["error"] = f"Failed to connect: {e}"
        return result

    atr = connection.getATR()
    result["atr"] = toHexString(atr)
    
    _, sw1, sw2 = transmit_apdu(connection, SELECT_PIV)
    
    certs = []
    all_emails = set()
    
    if sw1 == 0x90 and sw2 == 0x00:
        result["cardInfo"]["type"] = "PIV"
        for c in PIV_CERTS:
            lc = len(c["tag"])
            get_data_apdu = [0x00, 0xCB, 0x3F, 0xFF, lc] + c["tag"] + [0x00]
            response, sw1, sw2 = transmit_apdu(connection, get_data_apdu)
            if sw1 == 0x90 and sw2 == 0x00:
                cert_der = extract_cert_from_piv(response)
                if cert_der:
                    cert_dict = parse_certificate(cert_der, c["name"])
                    if cert_dict.get("subject"):
                        certs.append(cert_dict)
                        for e in cert_dict.get("emails", []):
                            all_emails.add(e)
    else:
        result["cardInfo"]["type"] = "DoD CAC (Legacy)"
        # Simple cert reading for CAC can be added here if needed

    try: connection.disconnect()
    except: pass
        
    result["success"] = True
    result["certs"] = certs
    result["allEmails"] = list(all_emails)
    return result
