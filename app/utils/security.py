import hashlib
import os

def hash_password(password: str) -> str:
    """
    Genera un hash seguro para la contraseña provista usando PBKDF2-SHA256 y sal (salt).
    Retorna el string con el formato 'sal:hash_hex'.
    """
    salt = os.urandom(16).hex()
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        salt.encode('utf-8'), 
        100000
    ).hex()
    return f"{salt}:{pwd_hash}"

def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifica una contraseña provista contra el hash guardado (formato 'sal:hash_hex').
    Retorna True si coincide, de lo contrario False.
    """
    try:
        if not hashed_password or ":" not in hashed_password:
            return False
        
        salt, pwd_hash = hashed_password.split(":")
        check_hash = hashlib.pbkdf2_hmac(
            'sha256', 
            password.encode('utf-8'), 
            salt.encode('utf-8'), 
            100000
        ).hex()
        return pwd_hash == check_hash
    except Exception:
        return False
