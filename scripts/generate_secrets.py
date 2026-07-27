import base64
import os

from passlib.context import CryptContext

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

print("DATA_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"))
print("LOOKUP_HMAC_KEY=" + base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"))
print("JWT_SECRET=" + base64.urlsafe_b64encode(os.urandom(48)).decode("ascii"))
print("ADMIN_PASSWORD_HASH=" + pwd.hash("troque-esta-senha"))
print("API_KEY_HASH=" + pwd.hash("troque-esta-api-key"))
