"""Абстракция реестра Windows: настоящий winreg + фейк для тестов/Linux."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

REG_SZ, REG_EXPAND_SZ, REG_BINARY, REG_DWORD, REG_MULTI_SZ, REG_QWORD = 1, 2, 3, 4, 7, 11

ROOTS = {
    "HKEY_CURRENT_USER": "HKCU",
    "HKEY_LOCAL_MACHINE": "HKLM",
    "HKEY_CLASSES_ROOT": "HKCR",
    "HKEY_USERS": "HKU",
}
ALIASES = {"HKCU": "HKEY_CURRENT_USER", "HKLM": "HKEY_LOCAL_MACHINE", "HKCR": "HKEY_CLASSES_ROOT", "HKU": "HKEY_USERS"}


def full_key(key: str) -> str:
    """HKCU\\Foo -> HKEY_CURRENT_USER\\Foo"""
    head, _, rest = key.partition("\\")
    head = ALIASES.get(head.upper(), head.upper())
    return head + ("\\" + rest if rest else "")


class RegistryBackend:
    """Интерфейс. Ключи — строки вида 'HKEY_CURRENT_USER\\Software\\X'."""

    def key_exists(self, key: str) -> bool: raise NotImplementedError
    def enum_keys(self, key: str) -> List[str]: raise NotImplementedError
    def enum_values(self, key: str) -> List[Tuple[str, Any, int]]: raise NotImplementedError
    def get_value(self, key: str, name: str) -> Optional[Tuple[Any, int]]: raise NotImplementedError
    def set_value(self, key: str, name: str, data: Any, typ: int) -> None: raise NotImplementedError
    def delete_value(self, key: str, name: str) -> None: raise NotImplementedError
    def delete_key(self, key: str) -> None: raise NotImplementedError


class WinRegistry(RegistryBackend):
    """Реализация поверх winreg (только Windows)."""

    def __init__(self):
        import winreg  # noqa: F401  (бросит ImportError вне Windows)
        self.w = __import__("winreg")
        self.roots = {
            "HKEY_CURRENT_USER": self.w.HKEY_CURRENT_USER,
            "HKEY_LOCAL_MACHINE": self.w.HKEY_LOCAL_MACHINE,
            "HKEY_CLASSES_ROOT": self.w.HKEY_CLASSES_ROOT,
            "HKEY_USERS": self.w.HKEY_USERS,
        }

    def _split(self, key: str):
        key = full_key(key)
        root, _, sub = key.partition("\\")
        return self.roots[root], sub

    def _open(self, key: str, write: bool = False):
        root, sub = self._split(key)
        access = self.w.KEY_READ | (self.w.KEY_WRITE if write else 0)
        return self.w.OpenKey(root, sub, 0, access)

    def key_exists(self, key):
        try:
            with self._open(key):
                return True
        except OSError:
            return False

    def enum_keys(self, key):
        out: List[str] = []
        try:
            with self._open(key) as h:
                i = 0
                while True:
                    try:
                        out.append(self.w.EnumKey(h, i))
                    except OSError:
                        break
                    i += 1
        except OSError:
            pass
        return out

    def enum_values(self, key):
        out = []
        try:
            with self._open(key) as h:
                i = 0
                while True:
                    try:
                        out.append(tuple(self.w.EnumValue(h, i)))
                    except OSError:
                        break
                    i += 1
        except OSError:
            pass
        return out

    def get_value(self, key, name):
        try:
            with self._open(key) as h:
                return self.w.QueryValueEx(h, name)
        except OSError:
            return None

    def set_value(self, key, name, data, typ):
        root, sub = self._split(key)
        with self.w.CreateKeyEx(root, sub, 0, self.w.KEY_WRITE) as h:
            self.w.SetValueEx(h, name, 0, typ, data)

    def delete_value(self, key, name):
        with self._open(key, write=True) as h:
            self.w.DeleteValue(h, name)

    def delete_key(self, key):
        for sub in self.enum_keys(key):
            self.delete_key(key + "\\" + sub)
        root, sub = self._split(key)
        self.w.DeleteKey(root, sub)


class FakeRegistry(RegistryBackend):
    """Реестр в памяти — для тестов и разработки на не-Windows."""

    def __init__(self):
        self.keys: Dict[str, Dict[str, Tuple[Any, int]]] = {}

    @staticmethod
    def _n(key: str) -> str:
        return full_key(key).rstrip("\\").lower()

    def add(self, key: str, values: Optional[Dict[str, Any]] = None) -> None:
        """add('HKCU\\\\Foo', {'': 'x', 'a': 1}); создаёт и родителей."""
        parts = full_key(key).split("\\")
        for i in range(1, len(parts) + 1):
            self.keys.setdefault("\\".join(parts[:i]), {})
        store = self.keys["\\".join(parts)]
        for name, data in (values or {}).items():
            typ = REG_DWORD if isinstance(data, int) else (REG_BINARY if isinstance(data, bytes) else REG_SZ)
            store[name] = (data, typ)

    def _find(self, key: str) -> Optional[str]:
        n = self._n(key)
        for k in self.keys:
            if k.lower() == n:
                return k
        return None

    def key_exists(self, key):
        return self._find(key) is not None

    def enum_keys(self, key):
        k = self._find(key)
        if k is None:
            return []
        prefix = k + "\\"
        out = []
        for other in self.keys:
            if other.startswith(prefix) and "\\" not in other[len(prefix):]:
                out.append(other[len(prefix):])
        return out

    def enum_values(self, key):
        k = self._find(key)
        if k is None:
            return []
        return [(n, d, t) for n, (d, t) in self.keys[k].items()]

    def get_value(self, key, name):
        k = self._find(key)
        if k is None:
            return None
        for n, v in self.keys[k].items():
            if n.lower() == name.lower():
                return v
        return None

    def set_value(self, key, name, data, typ):
        k = self._find(key)
        if k is None:
            self.add(key)
            k = self._find(key)
        self.keys[k][name] = (data, typ)

    def delete_value(self, key, name):
        k = self._find(key)
        if k is None:
            raise OSError("no key")
        for n in list(self.keys[k]):
            if n.lower() == name.lower():
                del self.keys[k][n]
                return
        raise OSError("no value")

    def delete_key(self, key):
        k = self._find(key)
        if k is None:
            raise OSError("no key")
        for other in [o for o in self.keys if o == k or o.startswith(k + "\\")]:
            del self.keys[other]


# ----------------------------------------------------------------------
# Экспорт в .reg (резервная копия перед исправлением)
# ----------------------------------------------------------------------
def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _hex(data: bytes, typ: Optional[int] = None) -> str:
    body = ",".join(f"{b:02x}" for b in data)
    prefix = "hex:" if typ in (None, REG_BINARY) else f"hex({typ:x}):"
    return prefix + body


def format_value(name: str, data: Any, typ: int) -> str:
    left = "@" if name == "" else f'"{_esc(name)}"'
    if typ == REG_SZ:
        return f'{left}="{_esc(str(data))}"'
    if typ == REG_DWORD:
        return f"{left}=dword:{int(data) & 0xFFFFFFFF:08x}"
    if typ == REG_EXPAND_SZ:
        return f"{left}={_hex((str(data) + chr(0)).encode('utf-16-le'), typ)}"
    if typ == REG_MULTI_SZ:
        items = list(data) if data else []
        raw = ("\0".join(items) + "\0\0").encode("utf-16-le") if items else b"\0\0\0\0"
        return f"{left}={_hex(raw, typ)}"
    if typ == REG_QWORD:
        return f"{left}={_hex(int(data).to_bytes(8, 'little'), typ)}"
    raw = bytes(data) if isinstance(data, (bytes, bytearray)) else b""
    return f"{left}={_hex(raw, typ if typ not in (REG_BINARY,) else None)}"


def export_key(reg: RegistryBackend, key: str, out: List[str]) -> None:
    key = full_key(key)
    if not reg.key_exists(key):
        return
    out.append(f"[{key}]")
    for name, data, typ in reg.enum_values(key):
        out.append(format_value(name, data, typ))
    out.append("")
    for sub in reg.enum_keys(key):
        export_key(reg, key + "\\" + sub, out)


def write_reg_file(reg: RegistryBackend, keys: List[str], path: str) -> None:
    lines: List[str] = ["Windows Registry Editor Version 5.00", ""]
    seen = set()
    for key in keys:
        k = full_key(key).lower()
        if k in seen:
            continue
        seen.add(k)
        export_key(reg, key, lines)
    with open(path, "w", encoding="utf-16", newline="") as fh:
        fh.write("\r\n".join(lines) + "\r\n")


def default_backend() -> Optional[RegistryBackend]:
    try:
        return WinRegistry()
    except Exception:
        return None
