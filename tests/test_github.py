import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from diffmind.github import GitHub


def test_app_jwt_uses_string_issuer_and_short_lifetime(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / 'app.pem'
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    gh = GitHub(123, path)
    token = gh.app_headers()['Authorization'].removeprefix('Bearer ')
    payload = jwt.decode(token, key.public_key(), algorithms=['RS256'], issuer='123')
    assert payload['exp'] - payload['iat'] == 600
