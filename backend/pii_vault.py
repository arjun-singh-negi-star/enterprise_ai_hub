import re
import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# =====================================================================
# 🔐 ENTERPRISE KEY MANAGEMENT (SIMULATED KMS)
# =====================================================================
# Production Rule: Never hardcode keys. Fetch from HashiCorp Vault, AWS KMS, or .env
# For this environment, we dynamically generate a 256-bit key if not provided in .env
_ENCRYPTION_KEY_B64 = os.getenv("ENTERPRISE_VAULT_AES_KEY")

if _ENCRYPTION_KEY_B64:
    _MASTER_KEY = base64.b64decode(_ENCRYPTION_KEY_B64)
else:
    # Generates a highly secure 256-bit (32 bytes) key for AES-256
    _MASTER_KEY = AESGCM.generate_key(bit_length=256)
    
# Initialize AES-GCM (Galois/Counter Mode) - Industry standard for secure authenticated encryption
aesgcm = AESGCM(_MASTER_KEY)

# =====================================================================
# 🛠️ CRYPTOGRAPHIC FUNCTIONS
# =====================================================================
def encrypt_pii(plaintext_str: str) -> str:
    """Encrypts raw data using AES-256-GCM with a random 96-bit nonce."""
    nonce = os.urandom(12)  # 96-bit nonce is standard for GCM
    # Encrypt the data
    ciphertext = aesgcm.encrypt(nonce, plaintext_str.encode('utf-8'), None)
    # Combine nonce and ciphertext, then encode to base64 for safe storage
    return base64.b64encode(nonce + ciphertext).decode('utf-8')

def decrypt_pii(encrypted_b64_str: str) -> str:
    """Decrypts base64 encoded AES-256 payload back to plain text."""
    try:
        data = base64.b64decode(encrypted_b64_str)
        nonce = data[:12]
        ciphertext = data[12:]
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except Exception as e:
        return f"[DECRYPTION_FAILED: Data Corrupted or Key Mismatch]"

# =====================================================================
# 🛡️ PII TOKENIZATION PIPELINE
# =====================================================================
def mask_pii(text: str, current_vault: dict) -> tuple:
    """
    Scans incoming text for emails (and other PII), replaces them with <TAGS>,
    and stores the ENCRYPTED real data in the vault.
    """
    if not isinstance(current_vault, dict):
        current_vault = {}

    secured_text = text
    
    # Standard Regex for identifying email addresses
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    found_emails = set(re.findall(email_pattern, text))
    
    email_counter = len([k for k in current_vault.keys() if "EMAIL_ADDRESS" in k]) + 1
    
    for email in found_emails:
        # Check if email is already encrypted in the vault
        already_exists = False
        for tag, encrypted_val in current_vault.items():
            if decrypt_pii(encrypted_val) == email:
                secured_text = secured_text.replace(email, tag)
                already_exists = True
                break
                
        if not already_exists:
            tag = f"<EMAIL_ADDRESS_{email_counter}>"
            # 🔥 CRITICAL UPDATE: Store the encrypted AES-256 string, NOT the plain text
            current_vault[tag] = encrypt_pii(email)
            secured_text = secured_text.replace(email, tag)
            email_counter += 1
            
    return secured_text, current_vault

def unmask_pii(text: str, current_vault: dict) -> str:
    """
    Takes an AI-generated draft containing <TAGS> and safely restores 
    the decrypted real data for outbound SMTP dispatch.
    """
    if not text or not current_vault:
        return text
        
    unmasked_text = text
    # Sort by length descending to prevent partial tag replacement bugs
    for tag, encrypted_val in sorted(current_vault.items(), key=lambda x: len(x[0]), reverse=True):
        # 🔥 CRITICAL UPDATE: Decrypt the payload before inserting it back into the text
        real_value = decrypt_pii(encrypted_val)
        unmasked_text = unmasked_text.replace(tag, real_value)
        
    return unmasked_text