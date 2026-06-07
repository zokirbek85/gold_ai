from src.core.security import hash_password, verify_password, create_access_token, decode_token


def test_hash_and_verify():
    pw = "S3cureP@ss!"
    h = hash_password(pw)
    assert verify_password(pw, h)


def test_jwt_roundtrip():
    token = create_access_token("user-1")
    data = decode_token(token)
    assert data.get("sub") == "user-1"
    assert data.get("type") == "access"
