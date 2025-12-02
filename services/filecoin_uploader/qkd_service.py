import logging
import random
import hashlib
import base64
import os
from typing import Tuple, List
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Configure logger
logger = logging.getLogger("qkd_service")

class QKDSimulator:
    def __init__(self):
        # Use AerSimulator for better performance and modern Qiskit compatibility
        self.backend = AerSimulator()

    def generate_random_bits(self, n: int) -> List[int]:
        return [random.randint(0, 1) for _ in range(n)]

    def generate_random_bases(self, n: int) -> List[str]:
        return [random.choice(['Z', 'X']) for _ in range(n)]

    def encode_qubits(self, bits: List[int], bases: List[str]) -> List[QuantumCircuit]:
        qubits = []
        for bit, base in zip(bits, bases):
            qc = QuantumCircuit(1, 1)
            if base == 'Z':
                if bit == 1:
                    qc.x(0)  # |1>
            elif base == 'X':
                if bit == 0:
                    qc.h(0)  # |+>
                else:
                    qc.x(0)
                    qc.h(0)  # |->
            qubits.append(qc)
        return qubits

    def measure_qubits(self, qubits: List[QuantumCircuit], bases: List[str]) -> List[int]:
        measured_bits = []
        for qc, base in zip(qubits, bases):
            # We need to copy the circuit to avoid modifying the original if we were to reuse it
            # But here we consume it.
            meas_qc = qc.copy()
            if base == 'X':
                meas_qc.h(0)
            meas_qc.measure(0, 0)
            
            # Execute
            result = self.backend.run(meas_qc, shots=1, memory=True).result()
            measured_bit = int(result.get_memory()[0])
            measured_bits.append(measured_bit)
        return measured_bits

    def sift_keys(self, alice_bases: List[str], bob_bases: List[str], bits: List[int]) -> List[int]:
        sifted_key = []
        for a_base, b_base, bit in zip(alice_bases, bob_bases, bits):
            if a_base == b_base:
                sifted_key.append(bit)
        return sifted_key

    def run_bb84_protocol(self, num_qubits: int = 100) -> List[int]:
        """
        Simulates the BB84 protocol to generate a shared secret key.
        Returns the sifted key bits.
        """
        logger.info(f"Starting BB84 protocol simulation with {num_qubits} qubits...")
        
        # 1. Alice generates bits and bases
        alice_bits = self.generate_random_bits(num_qubits)
        alice_bases = self.generate_random_bases(num_qubits)
        
        # 2. Alice encodes qubits
        encoded_qubits = self.encode_qubits(alice_bits, alice_bases)
        
        # 3. Bob generates bases and measures (Simulating transmission and measurement)
        bob_bases = self.generate_random_bases(num_qubits)
        bob_bits = self.measure_qubits(encoded_qubits, bob_bases)
        
        # 4. Sifting
        # Alice and Bob compare bases (publicly) and keep bits where bases match
        # We use Alice's bits for the key (perfect channel assumption for simulation)
        # In a real scenario with noise/Eve, they would compare a subset to check QBER.
        sifted_key = self.sift_keys(alice_bases, bob_bases, alice_bits)
        
        logger.info(f"BB84 completed. Raw key length: {len(sifted_key)}")
        return sifted_key

    def derive_aes_key(self, key_bits: List[int]) -> bytes:
        """
        Derives a 256-bit AES key from the QKD bits using SHA-256.
        """
        bit_str = "".join(map(str, key_bits))
        # Hash to get a fixed length 32-byte key
        digest = hashlib.sha256(bit_str.encode()).digest()
        return digest

    def encrypt_data(self, data: bytes) -> Tuple[bytes, bytes, bytes]:
        """
        Encrypts data using AES-GCM with a QKD-generated key.
        Returns: (ciphertext, nonce, tag, key)
        Wait, we need to return the key so it can be stored!
        """
        # Generate QKD key. 
        # We need enough bits to ensure entropy. 
        # 500 qubits usually give ~250 bits. SHA256 needs input entropy.
        # Let's use 500 qubits to be safe.
        qkd_bits = self.run_bb84_protocol(num_qubits=500)
        
        if not qkd_bits:
            raise ValueError("QKD failed to generate any key bits (bad luck?). Try again.")
            
        aes_key = self.derive_aes_key(qkd_bits)
        
        # Generate a random nonce (12 bytes for GCM)
        nonce = os.urandom(12)
        
        # Encrypt
        aesgcm = AESGCM(aes_key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        
        # AESGCM.encrypt returns ciphertext + tag appended in cryptography library?
        # No, wait. 
        # https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM.encrypt
        # "The ciphertext is the encryption of the data... The authentication tag is appended to the ciphertext."
        # So 'ciphertext' variable here actually contains both ciphertext and tag.
        
        return ciphertext, nonce, aes_key

    def decrypt_data(self, encrypted_data_with_tag: bytes, nonce: bytes, key: bytes) -> bytes:
        """
        Decrypts data using AES-GCM.
        """
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, encrypted_data_with_tag, None)
