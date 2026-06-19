"""Gestión de usuarios: autenticación, carpetas personales, validación.

Sistema simple: nombre + contraseña almacenados localmente en data/users.json
No hay encriptación pesada (es local, offline). Cada usuario tiene su carpeta
en knowledge/users/{username}/ donde se guardan sus documentos.

USUARIO MAESTRO: existe en todas las instalaciones, hardcodeado en el código.
Solo el propietario conoce la contraseña. Tiene acceso a todos los datos.
"""

import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime

from core.nlu import BASE_DIR, DATA_DIR


USERS_FILE = Path(DATA_DIR) / "users.json"
USERS_DIR  = Path(BASE_DIR) / "knowledge" / "users"

# ── Usuario Maestro ────────────────────────────────────────────────────────
# Nombre de usuario fijo. La contraseña real solo la conoce el propietario.
# El hash aquí es SHA256("GreenTail_Master_2024!") truncado a 32 chars.
# Para cambiar la contraseña, recalcula: hashlib.sha256(nueva.encode()).hexdigest()[:32]
MASTER_USERNAME = "gt_master"
MASTER_HASH     = "0c1f36246bc90ae67ded6950fa55dfbe"   # SHA256 de contraseña maestra


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()[:32]


def _ensure_dirs():
    USERS_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)


# ── Autenticación ──────────────────────────────────────────────────────────

def login(username: str, password: str) -> dict:
    """Autentica un usuario o el usuario maestro."""
    _ensure_dirs()

    # Verificar usuario maestro primero (funciona en toda instalación)
    if username == MASTER_USERNAME:
        if _hash_password(password) == MASTER_HASH:
            return {
                "success": True,
                "message": "Acceso maestro concedido",
                "user": {
                    "username": MASTER_USERNAME,
                    "folder":   str(Path(BASE_DIR) / "knowledge"),
                    "is_master": True,
                },
            }
        return {"success": False, "message": "Contraseña maestra incorrecta"}

    # Usuario normal
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)

    if username not in users:
        return {"success": False, "message": "Usuario no encontrado"}

    if users[username]["password_hash"] != _hash_password(password):
        return {"success": False, "message": "Contraseña incorrecta"}

    return {
        "success": True,
        "message": f"Bienvenido, {username}",
        "user": {
            "username":  username,
            "folder":    users[username]["folder"],
            "is_master": False,
        },
    }


def create_user(username: str, password: str) -> dict:
    """Crea un nuevo usuario regular."""
    _ensure_dirs()

    # Nombre reservado
    if username == MASTER_USERNAME:
        return {"success": False, "message": "Nombre de usuario reservado"}

    if not username or len(username) < 3:
        return {"success": False, "message": "El nombre debe tener al menos 3 caracteres"}

    if not password or len(password) < 4:
        return {"success": False, "message": "La contraseña debe tener al menos 4 caracteres"}

    if not all(c.isalnum() or c in "-_" for c in username):
        return {"success": False, "message": "Solo letras, números, - y _"}

    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)

    if username in users:
        return {"success": False, "message": f"El usuario '{username}' ya existe"}

    # Crea carpeta propia del usuario
    user_dir = USERS_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)

    users[username] = {
        "password_hash": _hash_password(password),
        "created":       datetime.now().isoformat(),
        "folder":        str(user_dir),
    }

    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

    return {
        "success": True,
        "message": f"Usuario '{username}' creado",
        "user": {"username": username, "folder": str(user_dir), "is_master": False},
    }


def get_user_folder(username: str) -> Path:
    """Devuelve la carpeta del usuario. El maestro tiene acceso a todo knowledge/."""
    if username == MASTER_USERNAME:
        return Path(BASE_DIR) / "knowledge"

    _ensure_dirs()
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)

    if username not in users:
        return None

    folder = Path(users[username]["folder"])
    try:
        folder.relative_to(USERS_DIR)   # previene path traversal
    except ValueError:
        return None

    return folder


def list_users() -> list:
    """Lista todos los usuarios regulares (sin contraseñas)."""
    _ensure_dirs()
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)

    result = []
    for u, data in users.items():
        result.append({
            "username":  u,
            "created":   data["created"],
            "folder":    data["folder"],
            "is_master": False,
        })
    return result


def delete_user(username: str, password: str) -> dict:
    """Elimina un usuario regular (requiere contraseña o acceso maestro)."""
    if username == MASTER_USERNAME:
        return {"success": False, "message": "No se puede eliminar el usuario maestro"}

    _ensure_dirs()
    auth = login(username, password)
    if not auth["success"]:
        # Permitir al maestro eliminar usuarios
        if login(MASTER_USERNAME, password).get("success"):
            pass  # maestro puede continuar
        else:
            return auth

    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)

    if username not in users:
        return {"success": False, "message": "Usuario no encontrado"}

    del users[username]
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

    return {"success": True, "message": f"Usuario '{username}' eliminado"}


def user_exists(username: str) -> bool:
    if username == MASTER_USERNAME:
        return True
    _ensure_dirs()
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
    return username in users


def is_master(username: str) -> bool:
    return username == MASTER_USERNAME
