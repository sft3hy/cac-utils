import sys
from smartcard.System import readers
from smartcard.util import toHexString
from cryptography import x509
from cryptography.hazmat.backends import default_backend
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

def print_separator():
    print("-" * 60)

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
    """
    Extracts the DER cert from the PIV object container wrapper
    The PIV object is a TLV sequence where tag 0x71 is the certificate
    """
    try:
        # Simple TLV parser just to find tag 0x71 (Certificate)
        i = 0
        if piv_data[i] == 0x53: # top level PIV wrapper
            i += 1
            length = piv_data[i]
            if length & 0x80:
                num_bytes = length & 0x7F
                i += 1 + num_bytes
            else:
                i += 1
            
            # Now inside the inner tags
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
                    # Found certificate
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
        "validity": {}
    }
    try:
        if len(cert_bytes) > 2 and cert_bytes[0] == 0x1f and cert_bytes[1] == 0x8b:
            import gzip
            try:
                cert_bytes = gzip.decompress(cert_bytes)
            except Exception as e:
                print(f"Failed to decompress {name} certificate: {e}")
                return result
                
        cert = x509.load_der_x509_certificate(cert_bytes, default_backend())
        
        # Extracts Emails from SAN
        try:
            san_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name_obj in san_ext.value:
                if isinstance(name_obj, x509.RFC822Name):
                    result["emails"].append(name_obj.value)
        except x509.ExtensionNotFound:
            pass

        for attr in cert.subject:
            result["subject"][attr.oid._name] = attr.value
            
        result["validity"] = {
            "notBefore": cert.not_valid_before_utc.strftime('%Y%m%d%H%M%SZ'),
            "notAfter": cert.not_valid_after_utc.strftime('%Y%m%d%H%M%SZ')
        }
        
    except Exception as e:
        print(f"Failed to parse X.509 certificate: {e}")
        
    return result


def read_cac_certificates(connection):
    certs = []
    
    # CAC Certificate file identifiers
    # 0200 = Identity, 0201 = Signature, 0202 = Encryption, etc.
    cac_files = [
        {"name": "CAC Identity", "id": [0x02, 0x00]},
        {"name": "CAC Signature", "id": [0x02, 0x01]},
        {"name": "CAC Encryption", "id": [0x02, 0x02]}
    ]
    
    for c in cac_files:
        # SELECT FILE
        select_apdu = [0x00, 0xA4, 0x02, 0x00, 0x02] + c["id"]
        response, sw1, sw2 = transmit_apdu(connection, select_apdu)
        
        if sw1 == 0x90 and sw2 == 0x00:
            # READ BINARY
            cert_data = bytearray()
            offset = 0
            
            while True:
                read_apdu = [0x00, 0xB0, (offset >> 8) & 0xFF, offset & 0xFF, 0x00] # Le=0 reads up to 256 bytes
                chunk, sw1, sw2 = transmit_apdu(connection, read_apdu)
                
                if sw1 == 0x90 and sw2 == 0x00:
                    cert_data.extend(chunk)
                    offset += len(chunk)
                    
                    if len(chunk) < 256:
                        break
                elif sw1 == 0x6B or sw1 == 0x6A:
                    break
                else:
                    break
                    
            if cert_data:
                try:
                    cert_dict = parse_certificate(bytes(cert_data), c["name"])
                    if cert_dict.get("subject"): # basic check if parse succeeded
                        certs.append(cert_dict)
                except ValueError as e:
                    if cert_data[0] == 0x70:
                        idx = 2
                        if cert_data[1] & 0x80:
                            idx += (cert_data[1] & 0x7F)
                        try:
                            cert_dict = parse_certificate(bytes(cert_data[idx:]), c["name"])
                            if cert_dict.get("subject"):
                                certs.append(cert_dict)
                        except Exception as e2:
                            pass
                        
    return certs


def read_card_data():
    """Main entry point for the API: returns a dictionary of card data."""
    result = {
        "success": False,
        "error": None,
        "reader": None,
        "atr": None,
        "cardInfo": {"protocol": "Unknown", "type": "Unknown"},
        "certs": [],
        "allEmails": []
    }

    # 1. List Readers
    r = readers()
    if not r:
        result["error"] = "No smart card readers found. Make sure it is connected."
        return result

    # 2. Connect to first reader
    reader = r[0]
    result["reader"] = str(reader)
    
    try:
        connection = reader.createConnection()
        connection.connect()
    except Exception as e:
        result["error"] = f"Failed to connect to card (Is a card inserted?): {e}"
        return result

    # 3. ATR
    atr = connection.getATR()
    result["atr"] = toHexString(atr)
    
    # Check Protocol if available
    try:
        prop = connection.getProperties()
        # Not all pyscard versions expose protocol easily, this is a fallback
        result["cardInfo"]["protocol"] = "T=1" if len(atr) > 0 and (atr[1] & 0x0F) == 1 else "T=0/T=1" 
    except:
        pass

    # 4. Try SELECT PIV applet
    _, sw1, sw2 = transmit_apdu(connection, SELECT_PIV)
    
    certs = []
    all_emails = set()
    
    if sw1 == 0x90 and sw2 == 0x00:
        result["cardInfo"]["type"] = "PIV"
        # 5. Read PIV Certificates
        for c in PIV_CERTS:
            lc = len(c["tag"])
            get_data_apdu = [0x00, 0xCB, 0x3F, 0xFF, lc] + c["tag"] + [0x00] # Le=0
            
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
        result["cardInfo"]["type"] = "DoD CAC"
        # Fallback to CAC logic
        cac_certs = read_cac_certificates(connection)
        for cert_dict in cac_certs:
            certs.append(cert_dict)
            for e in cert_dict.get("emails", []):
                    all_emails.add(e)
                    
    # Disconnect
    try:
        connection.disconnect()
    except:
        pass
        
    result["success"] = True
    result["certs"] = certs
    result["allEmails"] = list(all_emails)
    
    return result

if __name__ == "__main__":
    import json
    # For testing the refactor locally
    data = read_card_data()
    print(json.dumps(data, indent=2))

