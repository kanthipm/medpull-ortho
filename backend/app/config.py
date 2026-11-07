from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    # The console's one shared credential. Empty keeps every console route
    # open (the public demo); set, every console route needs
    # `Authorization: Bearer <token>` and the SPA asks for it on /login. The
    # patient app, the token-link pages and the webhooks are never behind it.
    console_access_token: str = ""
    # Webhook signing secrets — empty means that provider's deliveries are
    # rejected (verification fails closed; the mock/demo path needs none).
    terra_signing_secret: str = ""
    junction_webhook_secret: str = ""
    # The unsigned demo webhook (POST /api/webhooks/wearables/mock) trusts the
    # patient id in its body, so it exists only where a developer asks for it.
    # Off, the route answers 404 like any unknown provider.
    allow_mock_webhook: bool = False
    # True on the public demo stack only: the console shows the welcome and
    # the roster caption, and the seed may run. The real app leaves it off.
    demo_mode: bool = False
    # --- the home exercise program (app/hep) -------------------------------
    # Off hides the Exercise Plans nav and answers 404 on every /api/hep route.
    hep_enabled: bool = True
    # The hospital row the console's HEP library and plans belong to. Empty
    # picks the first active hospital; one shared console token means one
    # clinic per deployment until clinicians get their own logins.
    hep_clinic_id: str = ""
    # Junction (fka Vital), the wearable aggregator. The API key is the switch:
    # without it the registry reports Junction as needing setup and every
    # Junction endpoint answers 503, while signed deliveries to the webhook are
    # still verified and stored. Sandbox is the default on purpose — a
    # production key against a sandbox host (or the reverse) is a 401 from
    # Junction, never a silent cross-environment write.
    junction_api_key: str = ""
    junction_environment: str = "sandbox"  # sandbox | production
    junction_region: str = "us"  # us | eu
    junction_base_url: str = ""  # explicit override; derived from the two above when empty
    # Where Junction Link sends the patient after they connect a device. Empty
    # leaves them on Junction's own completion screen, which is fine for a
    # link handed over in clinic.
    junction_link_redirect_url: str = ""
    # Intraday heart-rate samples are the one Junction stream nothing in the
    # engine reads (ANALYZED_METRICS scores resting HR, not HR_SAMPLE) and the
    # one that dwarfs every other in volume — a day of Apple Watch samples is
    # thousands of rows. Off unless someone has a consumer for it.
    junction_ingest_heart_rate_samples: bool = False
    # Sendblue SMS/iMessage for care-team alerts. Both keys are the switch:
    # with either empty the SMS channel stays a logging stub, so the test
    # suite and a keyless checkout behave exactly as before the integration.
    sendblue_api_key: str = ""
    sendblue_api_secret: str = ""
    # Which of the account's Sendblue numbers sends. Optional: with one number
    # on the account Sendblue picks it, so empty stays valid.
    sendblue_from_number: str = ""
    # Care-team phone numbers, "id=+1...,id=+1..." (e.g. "ct_alvarez=+1512...").
    # Applied to care_team_members rows at startup so real numbers live in the
    # environment, never in the public repo. Empty applies nothing.
    care_team_phones: str = ""
    # Public base URL for patient check-in links; empty derives from the request.
    checkin_base_url: str = ""
    # Inbound Sendblue webhook. The secret is a path segment of the URL you
    # register at Sendblue (POST .../api/webhooks/sendblue/<secret>); with it
    # unset the route answers 503 and no inbound text is ever processed.
    sendblue_webhook_secret: str = ""
    # Sendblue's free shared-line plan refuses any number that has not texted
    # the line first ("This contact must be verified before sending messages
    # to it"). app/notifications/reachability.py learns which numbers can be
    # reached — from inbound texts, successful sends and the provider's own
    # contact list — and the apps ask a new patient to text MedPull once when
    # a code cannot go out yet. "auto" consults the account (plan + contact
    # list) before a first send; "true" always treats an unknown number as
    # needing that first text; "false" (a paid plan, another provider) skips
    # the lookup and simply attempts the send, learning from any refusal.
    sendblue_verified_contacts_only: str = "auto"  # auto | true | false
    # What the app pre-fills when it opens Messages for that first text. Any
    # text works; this one is friendly and unmistakable in the webhook log.
    sendblue_text_first_body: str = "Hi MedPull"
    # --- the patient app ---------------------------------------------------
    # Custom URL scheme the iOS app registers; task texts deep-link into it.
    mobile_app_scheme: str = "medpull"
    # Where the invite text sends a new patient to get the app. A placeholder
    # until the App Store listing exists; set APP_DOWNLOAD_URL to override.
    app_download_url: str = "https://medpull.org/app"
    # Onboarding can verify the phone with a texted code when Sendblue can
    # send one. Off by default (frictionless enrollment); set true to require
    # the code before a session is issued.
    mobile_otp_required: bool = False
    # A session the phone has not used for this long is revoked on its next
    # request and the app signs out (it already does so on any 401).
    session_idle_days: int = 90
    # apple-app-site-association: "<TEAMID>.<bundle id>" is served only when
    # the team id is set, so a deployment without the app publishes nothing.
    ios_team_id: str = ""
    ios_bundle_id: str = "com.medpull.recovery"
    # assetlinks.json, the Android equivalent: served only when the signing
    # certificate's SHA-256 fingerprints (comma-separated, colon-hex as the
    # Play Console prints them) are set.
    android_package: str = "com.medpull.recovery"
    android_cert_sha256: str = ""
    # --- the personal tier (app/personal) ---------------------------------
    # Every personal account starts on a trial this long; the paywall closes
    # after it unless an Apple subscription is on file.
    personal_trial_days: int = 14
    # Whether the trial and the App Store receipt decide access at all. Off
    # (the default) while there is no paid product: every personal account is
    # entitled, the apps show no plan step and no subscription rows, and the
    # receipt and notification code below sits dormant until this is true.
    personal_paywall: bool = False
    # The App Store product ids the iOS app sells (comma separated). A signed
    # transaction for any other product is refused.
    personal_product_ids: str = (
        "com.medpull.recovery.personal.monthly,com.medpull.recovery.personal.annual"
    )
    # How a StoreKit 2 signed transaction (JWS) is checked before it grants
    # access. "strict" verifies the x5c chain to Apple's root and the ES256
    # signature (needs the `cryptography` package and the pinned root below);
    # "lenient" decodes the payload and checks bundle id, product and expiry
    # only, recording the grant as unverified. Lenient is the default until
    # App Store Connect is live, because Xcode's local StoreKit testing signs
    # with a certificate Apple's chain cannot vouch for.
    apple_subscription_verify: str = "lenient"  # strict | lenient
    # Sandbox | Production: the environment a strict deployment accepts.
    # Sandbox transactions are always accepted too (App Review, TestFlight).
    apple_environment: str = "Sandbox"
    # SHA-256 of Apple Root CA - G3 (DER), the anchor a strict check pins.
    # Confirm against https://www.apple.com/certificateauthority/ before
    # turning strict mode on.
    apple_root_ca_g3_sha256: str = (
        "63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3653e9179"
    )
    # Local Ollama is OPT-IN (cloud-first product direction): leave the URL
    # empty and the chain is Groq -> deterministic fallback. Set OLLAMA_URL
    # explicitly to use a local model as the middle tier.
    ollama_url: str = ""
    ollama_model: str = "qwen3-vl-agent:latest"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'recovery.db'}"
    # The laptop's background warmer: every this many seconds it brings every
    # assessment up to date and fills any narrative the model has not written
    # yet, so a page load finds everything ready. 0 disables the loop (the
    # one-shot startup warm still runs). Off on Lambda with the startup warm.
    narrative_warm_interval_seconds: int = 300


settings = Settings()
