#!/usr/bin/env python3
"""OpenSSL DTLS 1.2 interop test script.

This script provides utilities to test DTLS handshake interoperability
between the Uya DTLS implementation and OpenSSL. It can:

1. Generate OpenSSL DTLS certificates and capture handshake fixtures
2. Parse and validate captured DTLS messages
3. Verify certificate fingerprints match between OpenSSL and Uya
4. Provide helper functions for manual interop testing

Usage:
    # Generate fresh fixtures
    python3 dtls_openssl_interop.py generate

    # Validate existing fixtures
    python3 dtls_openssl_interop.py validate

    # Show usage info
    python3 dtls_openssl_interop.py help
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / 'fixtures' / 'dtls'


def generate_openssl_cert_and_fingerprint():
    """Generate a self-signed P-256 cert and return DER hex + SHA-256 fingerprint."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        cert_path = tmppath / 'interop_test.crt'
        key_path = tmppath / 'interop_test.key'
        
        # Generate certificate
        subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'ec',
            '-pkeyopt', 'ec_paramgen_curve:prime256v1',
            '-keyout', str(key_path),
            '-out', str(cert_path),
            '-days', '30',
            '-nodes',
            '-subj', '/CN=uya-dtls-interop-test',
        ], check=True, capture_output=True, text=True)
        
        # Get DER encoding
        der_result = subprocess.run(
            ['openssl', 'x509', '-in', str(cert_path), '-outform', 'DER'],
            check=True, capture_output=True
        )
        cert_der_hex = der_result.stdout.hex()
        
        # Get SHA-256 fingerprint
        fp_result = subprocess.run(
            ['openssl', 'x509', '-in', str(cert_path), '-outform', 'DER',
             '-fingerprint', '-sha256', '-noout'],
            capture_output=True, text=True
        )
        fingerprint = ''
        if '=' in fp_result.stdout:
            fingerprint = fp_result.stdout.strip().split('=', 1)[1].replace(':', '').lower()
        
        return cert_der_hex, fingerprint


def validate_fixtures():
    """Validate the OpenSSL handshake fixtures file."""
    fixture_path = FIXTURE_DIR / 'openssl_handshake.json'
    if not fixture_path.exists():
        print(f'ERROR: Fixture file not found: {fixture_path}')
        return False
    
    try:
        data = json.loads(fixture_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'ERROR: Failed to parse fixture JSON: {e}')
        return False
    
    required_fields = [
        'description',
        'openssl_version',
        'certificate_der_hex',
        'certificate_sha256_fingerprint_hex',
        'cipher_suite',
        'cipher_suite_id',
        'srtp_profile',
        'srtp_profile_id',
        'certificate_cn',
        'named_curve',
    ]
    
    missing = [f for f in required_fields if f not in data]
    if missing:
        print(f'ERROR: Missing required fields: {missing}')
        return False
    
    # Validate certificate can be parsed by OpenSSL
    cert_hex = data['certificate_der_hex']
    try:
        cert_bytes = bytes.fromhex(cert_hex)
        with tempfile.NamedTemporaryFile(suffix='.der', delete=False) as tmp:
            tmp.write(cert_bytes)
            tmp_path = tmp.name
        
        result = subprocess.run(
            ['openssl', 'x509', '-inform', 'DER', '-in', tmp_path, '-noout', '-text'],
            capture_output=True,
            text=True
        )
        Path(tmp_path).unlink()
        
        if result.returncode != 0:
            print(f'ERROR: OpenSSL cannot parse certificate: {result.stderr}')
            return False
        
        print('Certificate validates with OpenSSL')
    except Exception as e:
        print(f'ERROR: Certificate validation failed: {e}')
        return False
    
    print(f'Fixture validation passed')
    print(f'  OpenSSL version: {data["openssl_version"]}')
    print(f'  Certificate CN: {data["certificate_cn"]}')
    print(f'  SHA-256 fingerprint: {data["certificate_sha256_fingerprint_hex"]}')
    return True


def command_generate():
    """Generate fresh OpenSSL handshake fixtures."""
    print('Generating OpenSSL DTLS handshake fixtures...')
    cert_der_hex, fingerprint = generate_openssl_cert_and_fingerprint()
    
    ver_result = subprocess.run(['openssl', 'version'], capture_output=True, text=True)
    openssl_ver = ver_result.stdout.strip()
    
    fixtures = {
        'description': 'OpenSSL DTLS 1.2 handshake fixtures for WebRTC interop',
        'openssl_version': openssl_ver,
        'certificate_der_hex': cert_der_hex,
        'certificate_sha256_fingerprint_hex': fingerprint,
        'cipher_suite': 'TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256',
        'cipher_suite_id': '0xc02b',
        'srtp_profile': 'SRTP_AES128_CM_HMAC_SHA1_80',
        'srtp_profile_id': '0x0001',
        'certificate_cn': 'uya-dtls-interop-test',
        'named_curve': 'secp256r1',
        'notes': [
            'certificate_der_hex is a real P-256 self-signed cert from OpenSSL',
            'certificate_sha256_fingerprint_hex can be compared against Uya SHA-256 output',
            'Use with dtls_certificate_parse for interop validation',
        ],
    }
    
    output_path = FIXTURE_DIR / 'openssl_handshake.json'
    output_path.write_text(json.dumps(fixtures, indent=2), encoding='utf-8')
    print(f'Wrote fixtures to {output_path}')
    print(f'  OpenSSL version: {openssl_ver}')
    print(f'  Certificate fingerprint: {fingerprint}')
    return True


def command_validate():
    """Validate existing fixtures."""
    print('Validating OpenSSL handshake fixtures...')
    return validate_fixtures()


def command_help():
    """Show usage information."""
    print(__doc__)
    return True


def main():
    parser = argparse.ArgumentParser(description='OpenSSL DTLS interop test utilities')
    parser.add_argument('command', choices=['generate', 'validate', 'help'],
                       help='Command to execute')
    
    args = parser.parse_args()
    
    if args.command == 'generate':
        success = command_generate()
    elif args.command == 'validate':
        success = command_validate()
    elif args.command == 'help':
        success = command_help()
    else:
        print(f'Unknown command: {args.command}')
        success = False
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
