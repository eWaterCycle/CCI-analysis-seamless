import json
from pathlib import Path
from typing import Annotated, Optional
from urllib.parse import parse_qs, urlparse

import requests
from conflator import CLIArg, ConfigModel, Conflator, EnvVar
from lxml import html
from pydantic import Field
import os
from dotenv import find_dotenv, load_dotenv

env_path = find_dotenv()
load_dotenv(env_path)
DESP_PASSWORD = os.getenv("PASSWORD_DESTINE")
DESP_USERNAME = os.getenv("USERNAME_DESTINE")

IAM_URL = "https://auth.destine.eu"
CLIENT_ID = "polytope-api-public"
REALM = "desp"
SERVICE_URL = "https://polytope.lumi.apps.dte.destination-earth.eu/"


def try_refresh_token(refresh_token: str) -> Optional[str]:
    """Exchange an existing refresh token for a new one without re-logging in.
    Returns the new refresh token, or None if the token is expired/invalid."""
    response = requests.post(
        IAM_URL + "/realms/" + REALM + "/protocol/openid-connect/token",
        data={
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "openid offline_access",
        },
    )
    if response.status_code == 200:
        data = response.json()
        # Prefer a new refresh token if one was returned (token rotation), else reuse existing
        return data.get("refresh_token") or refresh_token
    return None


class Config(ConfigModel):
    user: Annotated[
        Optional[str],
        Field(description="Your DESP username"),
        CLIArg("-u", "--user"),
        EnvVar("USER"),
    ] = None
    password: Annotated[
        Optional[str],
        Field(description="Your DESP password"),
        CLIArg("-p", "--password"),
        EnvVar("PASSWORD"),
    ] = None
    outpath: Annotated[
        str,
        Field(description='The file to write the token to (or "stdout")'),
        CLIArg("-o", "--outpath"),
    ] = str(Path().home() / ".polytopeapirc")


config = Conflator("despauth", Config).load()

if config.user is None:
    config.user = DESP_USERNAME
if config.password is None:
    config.password = DESP_PASSWORD

# --- Step 1: try to reuse an existing refresh token ---
token_path = Path(config.outpath)
if config.outpath != "stdout" and token_path.exists():
    try:
        existing_token = json.loads(token_path.read_text()).get("user_key")
        if existing_token:
            new_token = try_refresh_token(existing_token)
            if new_token:
                with open(config.outpath, "w") as file:
                    json.dump({"user_key": new_token}, file)
                print("Token refreshed successfully. No login required.")
                exit(0)
            else:
                print("Existing token expired or invalid. Performing full login...")
    except Exception:
        print("Could not read existing token. Performing full login...")

# --- Step 2: full credential login (only runs once or after token expiry) ---
with requests.Session() as s:
    # Get the auth url
    auth_url = (
        html.fromstring(
            s.get(
                url=IAM_URL + "/realms/" + REALM + "/protocol/openid-connect/auth",
                params={
                    "client_id": CLIENT_ID,
                    "redirect_uri": SERVICE_URL,
                    "scope": "openid offline_access",
                    "response_type": "code",
                },
            ).content.decode()
        )
        .forms[0]
        .action
    )

    # Login and get auth code
    login = s.post(
        auth_url,
        data={
            "username": config.user,
            "password": config.password,
        },
        allow_redirects=False,
    )

    # We expect a 302, a 200 means we got sent back to the login page (likely wrong credentials)
    if login.status_code == 200:
        tree = html.fromstring(login.content)
        error_message_element = tree.xpath('//span[@id="input-error"]/text()')
        error_message = (
            error_message_element[0].strip()
            if error_message_element
            else "Error message not found"
        )
        raise Exception(error_message)

    if login.status_code != 302:
        raise Exception("Login failed")

    auth_code = parse_qs(urlparse(login.headers["Location"]).query)["code"][0]

    # Use the auth code to get the token
    response = requests.post(
        IAM_URL + "/realms/" + REALM + "/protocol/openid-connect/token",
        data={
            "client_id": CLIENT_ID,
            "redirect_uri": SERVICE_URL,
            "code": auth_code,
            "grant_type": "authorization_code",
            "scope": "",
        },
    )

    if response.status_code != 200:
        raise Exception("Failed to get token")

    # Store the offline/refresh token — this is reused on all future runs
    token = response.json()["refresh_token"]

    if config.outpath != "stdout":
        with open(config.outpath, "w") as file:
            dico = {"user_key": token}
            json.dump(dico, file)
            print(f"Logged in. Token written to {config.outpath}")
    else:
        print(token)
