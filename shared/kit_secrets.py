"""kit_secrets: fetch a provider's credential by name, only when a call needs it.

Kit's model config never holds a credential. A provider names where one lives instead:

  "credential_env": "NAME"     an environment variable (works on every platform)
  "keychain_entry": "NAME"     the operating system's credential store:
                               macOS: a Keychain generic-password entry, read with
                                 `security find-generic-password -s NAME -w`
                               Windows: a Credential Manager generic credential named NAME, stored with
                                 `cmdkey /generic:NAME /user:kit /pass` (it asks for the value)

The environment variable wins when both are set and present. Local providers (Ollama, LM Studio,
and anything with "credential_required": false) need none.

The value is wrapped in a Credential: printing it, logging it, or putting it in an exception shows
"<credential: hidden>". Code that sends a request calls .reveal() at the last moment. Nothing here
writes a credential anywhere, and error messages name the entry, never the value.
"""
import os
import shutil
import subprocess
import sys

LOCAL_KINDS = {"ollama", "lmstudio", "local"}


class CredentialError(Exception):
    pass


class Credential:
    __slots__ = ("_value", "source")

    def __init__(self, value, source):
        self._value = value
        self.source = source            # "env NAME" or "keychain NAME", never the value

    def reveal(self):
        return self._value

    def __repr__(self):
        return f"<credential: hidden, from {self.source}>"

    __str__ = __repr__

    def __bool__(self):
        return bool(self._value)


def required(provider):
    if "credential_required" in provider:
        return bool(provider["credential_required"])
    return provider.get("kind") not in LOCAL_KINDS


def _wincred(entry):
    """A generic credential's secret from Windows Credential Manager (CredReadW)."""
    import ctypes
    from ctypes import wintypes

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                    ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                    ("UserName", wintypes.LPWSTR)]

    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        read, free = advapi32.CredReadW, advapi32.CredFree
    except (AttributeError, OSError):
        raise CredentialError("Windows Credential Manager isn't available") from None
    read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    read.restype = wintypes.BOOL
    free.argtypes = [ctypes.c_void_p]
    found = ctypes.POINTER(CREDENTIAL)()
    if not read(entry, 1, 0, ctypes.byref(found)):           # 1: CRED_TYPE_GENERIC
        raise CredentialError(f"no Windows Credential Manager entry '{entry}' (store it with "
                              f"cmdkey /generic:{entry} /user:kit /pass)")
    try:
        blob = ctypes.string_at(found.contents.CredentialBlob, found.contents.CredentialBlobSize)
    finally:
        free(found)
    # cmdkey and Credential Manager keep the secret as UTF-16; some tools store UTF-8 instead.
    if len(blob) % 2 == 0 and blob[1:2] == b"\x00":
        value = blob.decode("utf-16-le", errors="replace")
    else:
        value = blob.decode("utf-8", errors="replace")
    if not value.strip():
        raise CredentialError(f"Windows Credential Manager entry '{entry}' is empty")
    return value


def _keychain(entry):
    if os.name == "nt":
        return _wincred(entry)
    if sys.platform != "darwin":
        raise CredentialError(f"no Keychain on this platform (entry '{entry}'); use credential_env")
    tool = shutil.which("security")
    if not tool:
        raise CredentialError("the macOS `security` command isn't available")
    try:
        r = subprocess.run([tool, "find-generic-password", "-s", entry, "-w"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        raise CredentialError(f"couldn't read Keychain entry '{entry}'") from None
    if r.returncode != 0 or not r.stdout.strip():
        raise CredentialError(f"no Keychain entry '{entry}' (or access was refused)")
    return r.stdout.rstrip("\n")


def resolve(provider, name="provider"):
    """The provider's Credential, or None when it needs none. Raises CredentialError, naming only
    where it looked, when one is required and can't be found."""
    env = provider.get("credential_env")
    if env and os.environ.get(env):
        return Credential(os.environ[env], f"env {env}")
    entry = provider.get("keychain_entry")
    if entry:
        try:
            store = "credential-manager" if os.name == "nt" else "keychain"
            return Credential(_keychain(entry), f"{store} {entry}")
        except CredentialError:
            if required(provider):
                raise
            return None
    if not required(provider):
        return None
    store = "Credential Manager entry" if os.name == "nt" else "Keychain entry"
    where = " or ".join(x for x in (f"environment variable {env}" if env else "",
                                    f"{store} {entry}" if entry else "") if x)
    raise CredentialError(f"{name} needs a credential: set {where or 'credential_env or keychain_entry in models.json'}")
