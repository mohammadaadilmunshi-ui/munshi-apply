from pathlib import Path

path = Path("apps/native-host/src/munshi_apply_native/ai_settings.py")
text = path.read_text(encoding="utf-8")

old = '''    def set_api_key(self, api_key: object) -> None:
        if sys.platform != "darwin":
            raise ValueError("Secure desktop key entry currently requires macOS Keychain")
        if not isinstance(api_key, str) or len(api_key.strip()) < 20:
            raise ValueError("OpenAI API key is incomplete")
        result = subprocess.run(  # noqa: S603
            [
                "/usr/bin/security",
                "add-generic-password",
                "-a",
                _KEYCHAIN_ACCOUNT,
                "-s",
                _KEYCHAIN_SERVICE,
                "-w",
                api_key.strip(),
                "-U",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            raise ValueError("macOS Keychain rejected the OpenAI credential")
'''
new = '''    def set_api_key(self, api_key: object) -> None:
        if sys.platform != "darwin":
            raise ValueError("Secure desktop key entry currently requires macOS Keychain")
        if not isinstance(api_key, str) or len(api_key.strip()) < 20:
            raise ValueError("OpenAI API key is incomplete")
        cleaned_key = api_key.strip()
        password_hex = cleaned_key.encode("utf-8").hex()
        command = (
            f"add-generic-password -a {_KEYCHAIN_ACCOUNT} "
            f"-s {_KEYCHAIN_SERVICE} -U -X {password_hex}\\n"
        )
        result = subprocess.run(  # noqa: S603
            ["/usr/bin/security", "-q", "-i"],
            check=False,
            input=command,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            raise ValueError("macOS Keychain rejected the OpenAI credential")
'''

if old not in text:
    if 'password_hex = cleaned_key.encode("utf-8").hex()' not in text:
        raise SystemExit("set_api_key block not found")
else:
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
