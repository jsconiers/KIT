"""kit_secrets: fetch a provider's credential by name, only when a call needs it.

Kit's model config never holds a credential. A provider names where one lives instead:

  "credential_env": "NAME"     an environment variable (works on every platform)
  "keychain_entry": "NAME"     a macOS Keychain generic-password entry, read with
                               `security find-generic-password -s NAME -w`

The environment variable wins when both are set and present. Local providers (Ollama, LM Studio,
and anything with "credential_required": false) need none.

The value is wrapped in a Credential: printing it, logging it, or putting it in an exception shows
"<credential: hidden>". Code that sends a request calls .reveal() at the last moment. Nothing here
writes a credential anywhere, and error messages name the entry, never the value.

Windows Credential Manager isn't supported yet; set the environment variable instead.
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


def _keychain(entry):
    if sys.platform != "darwin":
        if os.name == "nt":
            raise CredentialError(f"Windows Credential Manager isn't supported yet (entry '{entry}'); "
                                  "set the provider's credential_env variable instead")
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
            return Credential(_keychain(entry), f"keychain {entry}")
        except CredentialError:
            if required(provider):
                raise
            return None
    if not required(provider):
        return None
    where = " or ".join(x for x in (f"environment variable {env}" if env else "",
                                    f"Keychain entry {entry}" if entry else "") if x)
    raise CredentialError(f"{name} needs a credential: set {where or 'credential_env or keychain_entry in models.json'}")
