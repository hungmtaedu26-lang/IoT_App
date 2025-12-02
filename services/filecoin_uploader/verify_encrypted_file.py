import os
import sys
import base64
import json
import logging
import mysql.connector
from pathlib import Path
from datetime import datetime

try:
    from qkd_service import QKDSimulator
except ImportError:
    # Fallback for local testing if needed, though inside container this isn't needed
    import sys
    sys.path.append(os.path.join(os.getcwd()))
    try:
        from qkd_service import QKDSimulator
    except ImportError:
        print("Could not import QKDSimulator.")
        sys.exit(1)

# Configuration
MYSQL_HOST = os.getenv("MYSQL_HOST", "mariadb")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "iot_data")
MYSQL_USER = os.getenv("MYSQL_USER", "myuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "mypassword")
FILECOIN_DIR = Path(os.getenv("FILECOIN_DIR", "/app/data/filecoin"))
ENCRYPTED_DIR = FILECOIN_DIR / "encrypted"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_enc")

def connect_db():
    return mysql.connector.connect(
        host=MYSQL_HOST,
        database=MYSQL_DATABASE,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
    )

def get_key_from_db(trace_id):
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT enc_key, nonce FROM qkd_keys WHERE trace_id = %s"
        cursor.execute(query, (trace_id,))
        result = cursor.fetchone()
        return result
    finally:
        conn.close()

def verify_file(trace_id):
    logger.info(f"Verifying encryption for Trace ID: {trace_id}")
    
    # 1. Get Key from DB
    key_record = get_key_from_db(trace_id)
    if not key_record:
        logger.error("Key not found in database!")
        return False
    
    enc_key = base64.b64decode(key_record['enc_key'])
    nonce = base64.b64decode(key_record['nonce'])
    logger.info("Key and Nonce retrieved from DB.")

    # 2. Find Encrypted File
    # Try to find file matching the trace_id
    # Filename format: {trace_id}_encrypted.bin (assuming trace_id is part of filename)
    # Actually trace_id is usually like MAC_DATE, and filename is MAC_DATE.json -> MAC_DATE_encrypted.bin
    filename = f"{trace_id}_encrypted.bin"
    file_path = ENCRYPTED_DIR / filename
    
    if not file_path.exists():
        logger.error(f"Encrypted file not found at: {file_path}")
        logger.info(f"Checking {FILECOIN_DIR} just in case...")
        fallback_path = FILECOIN_DIR / filename
        if fallback_path.exists():
            file_path = fallback_path
            logger.info(f"Found at {fallback_path}")
        else:
            return False

    logger.info(f"Found encrypted file: {file_path}")
    
    # 3. Decrypt
    try:
        with open(file_path, "rb") as f:
            encrypted_data = f.read()
            
        qkd = QKDSimulator()
        decrypted_data = qkd.decrypt_data(encrypted_data, nonce, enc_key)
        
        logger.info("Decryption SUCCESSFUL!")
        
        # Try to parse as JSON to verify it's the transcript
        try:
            transcript = json.loads(decrypted_data)
            logger.info("Decrypted content is valid JSON.")
            print("\n--- DECRYPTED TRANSCRIPT CONTENT ---")
            print(json.dumps(transcript, indent=2))
            print("------------------------------------\n")
        except json.JSONDecodeError:
            logger.warning("Decrypted content is NOT valid JSON (but decryption didn't fail).")
            print(decrypted_data)
            
        return True
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_encrypted_file.py <trace_id>")
        print("Example: python verify_encrypted_file.py 90:15:06:D7:36:D4_2025-12-02")
        sys.exit(1)
    
    trace_id = sys.argv[1]
    verify_file(trace_id)
