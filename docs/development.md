# Development

## Releases

Every change to `backend/` on `main` builds the APKs and the Docker image in GitHub Actions ([`release.yml`](../.github/workflows/release.yml)):

1. builds the TV helper and the phone app (`backend/android/build.py`, signed with keys from repository secrets),
2. builds and pushes `ghcr.io/<owner>/homemote-backend` with the APKs inside (`/opt/homemote/apk`), tagged `latest`, the version and the commit,
3. for a new version in [`backend/app/version.py`](../backend/app/version.py) creates a GitHub Release `v<version>` with both APKs and the notes from [`CHANGELOG.md`](../CHANGELOG.md).

The direct download links in the README (`releases/latest/download/homemote.apk`, `…/helper.apk`) always point to the newest release.

## Signing keys

Android only installs an update over an existing app when both are signed with the same key, so the APKs are signed with fixed keystores stored as repository secrets:

| Secret | Content |
|---|---|
| `HM_KEY_HELPER` | base64 of `homemote-helper.jks` |
| `HM_KEY_PHONE` | base64 of `homemote-phone.jks` |

Repository → Settings → Secrets and variables → Actions → *New repository secret*. To get the base64 text: `base64 -w0 homemote-helper.jks`. A fork without existing installs can create new keystores by running `python3 backend/android/build.py` once locally (needs JDK 17+); they appear in `backend/android/*/keystore/`. Never commit keystores.

## Build from source

```sh
docker build -t ghcr.io/tlkounev/homemote-backend:latest backend
docker compose up -d
```

Without prebuilt APKs in the image the backend builds them itself at first start (installs a JDK, downloads the build tools, keeps keystores in `data/keys/`). No Gradle or Android SDK is used, see [`backend/android/README.md`](../backend/android/README.md).

## Project layout

| Path | What |
|---|---|
| `backend/app/` | Python backend (aiohttp), web UI in `static/` (Czech and English inline, other languages in `static/i18n/`) |
| `backend/android/helper/` | helper app for the TV |
| `backend/android/phone/` | phone app (WebView wrapper with QR pairing) |
| `backend/android/build.py` | APK build without Gradle |
| `docs/screenshots/` | README screenshots (demo data, placeholder app images) |
| `docker-compose.yml` | ready-to-use Compose file |

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `888` | web UI and API port |
| `DATA_DIR` | `/data` | state, pairing certificate, sign-ins |
| `LOG_LEVEL` | `INFO` | log level |
| `ADVERTISE_IP` | auto | IP announced over mDNS and used in the local address |
| `HM_UPDATE_CHECK` | `1` | `0` turns off the new-version check |
| `HM_UPDATE_REPO` | `tlkounev/homemote` | repository whose releases are checked |
| `HM_APK_DIR` | `/opt/homemote/apk` | prebuilt APKs in the image |
| `HM_BUILD_APKS` | `1` | `0` turns off building APKs at start (source builds only) |
