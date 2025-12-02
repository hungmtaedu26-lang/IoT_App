import sys
import os
import logging

# Add the service directory to path so we can import qkd_service
sys.path.append(os.path.join(os.getcwd(), 'services', 'filecoin_uploader'))

try:
    from qkd_service import QKDSimulator
except ImportError:
    print("Could not import QKDSimulator. Make sure you are running this from the project root and requirements are installed.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verification")

def test_qkd_flow():
    logger.info("Initializing QKDSimulator...")
    qkd = QKDSimulator()
    
    original_data = b"This is a secret message for Filecoin storage."
    logger.info(f"Original Data: {original_data}")
    
    # Test Encryption
    logger.info("Running QKD and Encrypting...")
    try:
        encrypted_data, nonce, key = qkd.encrypt_data(original_data)
        logger.info(f"Encryption successful.")
        logger.info(f"Key (hex): {key.hex()}")
        logger.info(f"Nonce (hex): {nonce.hex()}")
        logger.info(f"Encrypted Data (hex): {encrypted_data.hex()}")
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return False

    # Test Decryption
    logger.info("Decrypting...")
    try:
        decrypted_data = qkd.decrypt_data(encrypted_data, nonce, key)
        logger.info(f"Decrypted Data: {decrypted_data}")
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return False
        
    if original_data == decrypted_data:
        logger.info("SUCCESS: Decrypted data matches original data.")
        return True
    else:
        logger.error("FAILURE: Decrypted data does NOT match original data.")
        return False

if __name__ == "__main__":
    print("--- Starting QKD Integration Verification ---")
    if test_qkd_flow():
        print("\nVerification PASSED!")
    else:
        print("\nVerification FAILED!")
