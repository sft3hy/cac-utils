import sys
from smartcard.System import readers

# Standard CAC ADF Selection
# A0 00 00 00 79 03 00 (DoD CAC)
CAC_AID = [0xA0, 0x00, 0x00, 0x00, 0x79, 0x03, 0x00]

# Known CAC EFs
EF_CERTS = [
    {"name": "Identity", "p1p2": [0x02, 0x00]},
    {"name": "Signature", "p1p2": [0x02, 0x01]},
    {"name": "Encryption", "p1p2": [0x02, 0x02]}
]

def apdu_cmd(cmd, p1, p2, data=[]):
    return [0x00, cmd, p1, p2, len(data)] + data

def get_response(conn, sw2):
    get_resp = [0x00, 0xC0, 0x00, 0x00, sw2]
    return conn.transmit(get_resp)

def try_select(conn, name, aid):
    select_cmd = [0x00, 0xA4, 0x04, 0x00, len(aid)] + aid
    print(f"\nTrying {name} (AID: {' '.join(f'{x:02X}' for x in aid)})...")
    resp, sw1, sw2 = conn.transmit(select_cmd)
    
    if sw1 == 0x61:
        print(f"  -> SUCCESS (61 {sw2:02X}). Sending GET RESPONSE...")
        resp, sw1, sw2 = get_response(conn, sw2)
        print(f"  -> Data: {' '.join(f'{x:02X}' for x in resp)} (SW={sw1:02X} {sw2:02X})")
        return True
    elif sw1 == 0x90:
        print(f"  -> SUCCESS (90 00)")
        return True
    else:
        print(f"  -> FAILED (SW: {sw1:02X} {sw2:02X})")
        return False

def main():
    r = readers()
    if not r:
        print("No readers found.")
        sys.exit(1)
        
    reader = r[0]
    print(f"Connecting to: {reader}")
    conn = reader.createConnection()
    conn.connect()
    
    AIDs = {
        "DoD CAC Applet": [0xA0, 0x00, 0x00, 0x00, 0x79, 0x03, 0x00],
        "DoD CAC PKI Applet": [0xA0, 0x00, 0x00, 0x00, 0x79, 0x01, 0x00],
        "DoD CAC PKI Applet (2)": [0xA0, 0x00, 0x00, 0x00, 0x79, 0x01, 0x01],
        "DoD CAC PKI Applet (3)": [0xA0, 0x00, 0x00, 0x00, 0x79, 0x01, 0x02],
        "PIV Applet": [0xA0, 0x00, 0x00, 0x03, 0x08, 0x00, 0x00, 0x10, 0x00],
    }
    
    for name, aid in AIDs.items():
        try_select(conn, name, aid)

if __name__ == "__main__":
    main()
