import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
BOT_ADMIN_ID: int = int(os.getenv("BOT_ADMIN_ID", "0"))
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8080"))
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "/data/license.db")
SITE_URL: str = os.getenv("SITE_URL", "")
PUBLIC_URL: str = os.getenv("PUBLIC_URL", "")
PACKAGES_DIR: str = os.getenv("PACKAGES_DIR", "/packages")
LICENSE_SERVER_URL: str = os.getenv("LICENSE_SERVER_URL", "https://rs-license.dfc-online.com")
GITHUB_PAT: str = os.getenv("GITHUB_PAT", "")
GITHUB_REPO: str = os.getenv("GITHUB_REPO", "DanteFuaran/Remnasale")
GITHUB_BRANCH: str = os.getenv("GITHUB_BRANCH", "lic")
