import base64
import os
import sys

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    print("Error: 'cryptography' library is not installed.")
    print("Please install it using: pip install cryptography")
    sys.exit(1)

def decrypt_manual():
    print("--- Manual QKD Decryption Tool ---")
    print("This tool decrypts files using the Key and Nonce from your database (DBeaver).")
    
    # 1. Get File Path
    file_path = input("\nEnter path to encrypted file (e.g., C:\\Downloads\\..._encrypted.bin): ").strip().strip('"')
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    # 2. Get Key
    key_b64 = input("Enter 'enc_key' from DBeaver (Base64 string): ").strip()
    try:
        key = base64.b64decode(key_b64)
    except Exception as e:
        print(f"Error decoding key: {e}")
        return

    # 3. Get Nonce
    nonce_b64 = input("Enter 'nonce' from DBeaver (Base64 string): ").strip()
    try:
        nonce = base64.b64decode(nonce_b64)
    except Exception as e:
        print(f"Error decoding nonce: {e}")
        return

    # 4. Decrypt
    try:
        with open(file_path, "rb") as f:
            encrypted_data = f.read()

        aesgcm = AESGCM(key)
        decrypted_data = aesgcm.decrypt(nonce, encrypted_data, None)
        
        print("\nSUCCESS! Decryption successful.")
        
        # Save decrypted file
        out_path = file_path + ".decrypted.json"
        with open(out_path, "wb") as f:
            f.write(decrypted_data)
            
        print(f"Decrypted content saved to: {out_path}")
        
        # Print content if it looks like text
        try:
            print("\n--- Content Preview ---")
            print(decrypted_data.decode('utf-8')[:500] + "...")
        except:
            print("(Content is binary or not UTF-8 text)")

    except Exception as e:
        print(f"\nFAILED: Decryption failed. Error: {e}")
        print("Possible causes:")
        print("- Wrong Key or Nonce")
        print("- File is corrupted")
        print("- Key/Nonce does not match this file")

if __name__ == "__main__":
    decrypt_manual()
