from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    facebook_base_url: str = getenv(
        "FB_BASE_URL",
        "https://www.facebook.com/",
    )
    facebook_profile_path: str = getenv(
        "FB_PROFILE_PATH",
        "./data/facebook-profile",
    )
    facebook_headless: bool = getenv(
        "FB_HEADLESS",
        "false",
    ).lower() == "true"


settings = Settings()