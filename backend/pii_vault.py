import os
from typing import Tuple, Dict
from cryptography.fernet import Fernet
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine

# =====================================================================
# 🔐 ENCRYPTION SETUP (FERNET SYMMETRIC CRYPTOGRAPHY)
# Generates a volatile key for the session if not provided in .env.
# In true production, this key is rotated and stored in HashiCorp Vault/KMS.
# =====================================================================
ENCRYPTION_KEY = os.getenv("PII_ENCRYPTION_KEY", Fernet.generate_key().decode())
cipher_suite = Fernet(ENCRYPTION_KEY.encode())

# =====================================================================
# 🧠 NLP ENGINE INITIALIZATION
# =====================================================================
analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

# Custom Format Recognition (Example: B2B Project IDs)
emp_pattern = Pattern(name="employee_id_pattern", regex=r"\bEMP-\d{4}\b", score=0.8)
emp_recognizer = PatternRecognizer(supported_entity="CUSTOM_EMP_ID", patterns=[emp_pattern])
analyzer.registry.add_recognizer(emp_recognizer)

# Encryption Helpers
def encrypt_val(val: str) -> str:
    return cipher_suite.encrypt(val.encode()).decode()

def decrypt_val(val: str) -> str:
    return cipher_suite.decrypt(val.encode()).decode()

def mask_pii(text: str, existing_vault: Dict[str, str] = None, strict_block: bool = False) -> Tuple[str, Dict[str, str]]:
    """
    NLP PII detection. 
    - strict_block=True: Instantly crashes the flow if SSN/Credit Card is found.
    - Encrypts original data before saving it to the LangGraph state.
    """
    pii_vault = existing_vault.copy() if existing_vault else {}
    masked_text = text
    
    if not text:
        return "", pii_vault

    system_blacklist = {
        "best regards", "thank you", "vector knowledge", "knowledge base",
        "corporate communication", "system reasoning", "thinking analytics",
        "official corporate", "client pipeline", "execution engine"
    }

    results = analyzer.analyze(
        text=text,
        language='en',
        entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "US_BANK_NUMBER", "CUSTOM_EMP_ID"]
    )

    unique_matches = {}
    for res in results:
        match_str = text[res.start:res.end].strip()
        if not match_str or match_str.lower() in system_blacklist:
            continue
            
        ent_type = res.entity_type

        # 🛑 ENTERPRISE STRICT MODE: Hard block on PCI/DSS data
        if strict_block and ent_type in ["CREDIT_CARD", "US_SSN", "US_BANK_NUMBER"]:
            raise ValueError(f"🚨 SECURITY ALERT: High-risk data ({ent_type}) detected. Transaction forcefully blocked.")

        if ent_type not in unique_matches:
            unique_matches[ent_type] = set()
        unique_matches[ent_type].add(match_str)

    counters = {k: 1 for k in unique_matches.keys()}
    for key in pii_vault.keys():
        for ent_type in unique_matches.keys():
            if f"<{ent_type}_" in key:
                counters[ent_type] += 1

    for ent_type, matches in unique_matches.items():
        for match in sorted(matches, key=len, reverse=True):
            
            # Decrypt existing vault values temporarily to check for duplicates
            existing_token = None
            for t, enc_v in pii_vault.items():
                if decrypt_val(enc_v) == match:
                    existing_token = t
                    break
            
            if existing_token:
                masked_text = masked_text.replace(match, existing_token)
            else:
                token = f"<{ent_type}_{counters[ent_type]}>"
                # 🔐 ENCRYPT BEFORE STORING IN STATE
                pii_vault[token] = encrypt_val(match)
                masked_text = masked_text.replace(match, token)
                counters[ent_type] += 1

    return masked_text, pii_vault

def unmask_pii(masked_draft: str, pii_vault: Dict[str, str]) -> str:
    """Decrypts vault values and restores the UI/SMTP payload."""
    if not masked_draft or not pii_vault:
        return masked_draft or ""
        
    clean_draft = masked_draft
    # Decrypt the vault temporarily for processing
    decrypted_vault = {token: decrypt_val(enc_v) for token, enc_v in pii_vault.items()}
    
    for token, original_value in sorted(decrypted_vault.items(), key=lambda x: len(x[1]), reverse=True):
        clean_draft = clean_draft.replace(token, original_value)
        
    return clean_draft

def remask_pii(edited_text: str, pii_vault: Dict[str, str], strict_block: bool = False) -> Tuple[str, Dict[str, str]]:
    """UI Boundary logic handling decryption/encryption translation."""
    if not edited_text:
        return "", pii_vault
    if pii_vault is None:
        pii_vault = {}
        
    re_masked = edited_text
    decrypted_vault = {token: decrypt_val(enc_v) for token, enc_v in pii_vault.items()}
    
    for token, original_value in sorted(decrypted_vault.items(), key=lambda x: len(x[1]), reverse=True):
        if original_value in re_masked:
            re_masked = re_masked.replace(original_value, token)
            
    fully_masked, updated_vault = mask_pii(re_masked, pii_vault, strict_block)
    
    return fully_masked, updated_vault