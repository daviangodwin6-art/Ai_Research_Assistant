import os

import requests
from dotenv import load_dotenv

load_dotenv()

SIGN_UP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
SIGN_IN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"

ERROR_MESSAGES = {
    "EMAIL_EXISTS": "An account with this email already exists.",
    "EMAIL_NOT_FOUND": "No account found for that username or email.",
    "INVALID_PASSWORD": "Incorrect password.",
    "INVALID_LOGIN_CREDENTIALS": "Incorrect username/email or password.",
    "WEAK_PASSWORD": "Password is too weak.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Try again later.",
    "USER_DISABLED": "This account has been disabled.",
    "OPERATION_NOT_ALLOWED": "Email/password sign-in is not enabled in Firebase Authentication.",
    "INVALID_EMAIL": "That email address is not valid.",
    "MISSING_PASSWORD": "Password is required.",
}


def api_key() -> str:
    return (os.getenv("FIREBASE_API_KEY") or "").strip()


def _friendly_error(payload: dict) -> str:
    message = (
        payload.get("error", {}).get("message", "Authentication failed.")
        if isinstance(payload, dict)
        else "Authentication failed."
    )
    code = str(message).split(":")[0].strip()
    return ERROR_MESSAGES.get(code, str(message))


def sign_up(email: str, password: str) -> dict:
    key = api_key()
    if not key:
        raise RuntimeError("FIREBASE_API_KEY is missing. Add it to your .env file.")
    response = requests.post(
        SIGN_UP_URL,
        params={"key": key},
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=20,
    )
    data = response.json()
    if not response.ok:
        raise RuntimeError(_friendly_error(data))
    return data


def sign_in(email: str, password: str) -> dict:
    key = api_key()
    if not key:
        raise RuntimeError("FIREBASE_API_KEY is missing. Add it to your .env file.")
    response = requests.post(
        SIGN_IN_URL,
        params={"key": key},
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=20,
    )
    data = response.json()
    if not response.ok:
        raise RuntimeError(_friendly_error(data))
    return data
