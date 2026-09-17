"""Check the tracked-file boundary without printing file contents or secrets."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {'.git', '.codex', 'DUMP', 'node_modules', '.venv', '.prerender', 'dist', 'local-data', 'outputs', 'inputs', 'debug', 'logs'}
FORBIDDEN_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.bundle', '.dump', '.sqlite', '.sqlite3', '.zip', '.log'}


def main() -> int:
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    errors = []
    count = 0
    for name in filter(None, paths):
        count += 1
        path = Path(name)
        if FORBIDDEN_PARTS.intersection(path.parts) or path.suffix in FORBIDDEN_SUFFIXES:
            errors.append((name, 'private/generated file must not be tracked'))
        if path.name.startswith('.env') and path.name != '.env.example':
            errors.append((name, 'only .env.example may be tracked'))
        if re.search(r'(cred|service[-_]account).*\.json$', path.name, re.I):
            errors.append((name, 'credential-file name'))
        data = (ROOT / path).read_bytes()
        if b'\0' in data:
            continue
        if re.search(rb'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----', data):
            errors.append((name, 'private key marker'))
        if re.search(rb'"type"\s*:\s*"service_account"', data) and b'"private_key"' in data:
            errors.append((name, 'service account credentials'))
    for path, reason in errors:
        print(f'{path}: {reason}')
    if not count:
        print('No tracked files; stage the proposed snapshot before checking')
        return 1
    if errors:
        return 1
    print(f'Checked publication boundary for {count} tracked files')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
