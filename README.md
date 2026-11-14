# Homemote for Google TV

A self-hosted universal remote for Google TV / Android TV devices. A small backend runs in Docker on your home server, finds the TVs on your network and serves a web remote plus an Android phone app.

- **Remote control** over the Android TV Remote protocol v2 (the same one the official Google TV app uses): D-pad, volume, channels, long-press OK, power, typing text (also into apps with their own on-screen keyboard, via ADB).
- **Optional helper app on the TV** adds the app list with icons, now playing with a seek bar, input selection and opening TV settings.
- **Phone app** (Android): pairs by scanning a QR code, picks the local or public address automatically, and the phone's volume keys control the TV.
- Several TVs in tabs, 15 UI languages, access from the internet through your own reverse proxy.

## Install

Any x86-64 Linux host with Docker (home server, mini PC, NAS with Docker support). The image `ghcr.io/tlkounev/homemote-backend` contains everything, including the ready-built helper and phone APKs. It is built for `linux/amd64`.

### Docker Compose

Copy [`docker-compose.yml`](docker-compose.yml) into an empty folder and run:

```sh
docker compose up -d                          # first start
docker compose pull && docker compose up -d   # update
```

### docker run

```sh
docker run -d --name homemote-backend --restart unless-stopped \
  --network host -v "$PWD/data:/data" -e PORT=888 \
  ghcr.io/tlkounev/homemote-backend:latest
```

Then open `http://<host IP>:888/` **from your home network** and set a password. All state lives in the `data` folder (mounted at `/data`).

### Network

`network_mode: host` is required for automatic TV discovery (mDNS): the container has to be directly in the home LAN, and Docker's default NAT network does not pass multicast. Docker Desktop on Windows/macOS does not pass multicast into the LAN either; add TVs by IP there (the **+** button).

To give the container its own IP in the LAN instead, use a `macvlan` network:

```yaml
services:
  homemote-backend:
    # … as in docker-compose.yml, without network_mode
    networks:
      lan:
        ipv4_address: 192.168.1.20      # outside the DHCP pool
networks:
  lan:
    driver: macvlan
    driver_opts: { parent: eth0 }        # host interface in the LAN (ip -br a)
    ipam:
      config:
        - subnet: 192.168.1.0/24
          gateway: 192.168.1.1
```

With `macvlan` the Docker host itself cannot reach the container unless you add a macvlan interface on the host too; other devices in the LAN can.

## First steps

1. The backend finds powered-on TVs by itself; the **+** button in the header starts blinking. Add the TV, press **Pair** and enter the code shown on the TV. TVs can also be added by IP.
2. Optional: install the helper on the TV (apps section → ⋯ → **Device helper**). It is installed once over ADB debugging; the dialog explains how to enable it.
3. Add a phone: Settings → Signed-in phones and browsers → **Add a phone**. Scan the first QR code to download the app, then scan the second one in the app.
4. For access from the internet, set the reverse-proxy address in Settings → Backend addresses. The proxy must pass WebSockets (`/api/ws`).

Forgotten password: stop the container, delete `data/auth.json`, start it again.

## Releases

Every change to `backend/` on `main` builds the APKs and the Docker image in GitHub Actions ([`release.yml`](.github/workflows/release.yml)). A new version in [`backend/app/version.py`](backend/app/version.py) also creates a GitHub Release with both APKs. Changes are listed in [`CHANGELOG.md`](CHANGELOG.md); the HTTP/WebSocket API is documented in [`API.md`](API.md).

### Signing keys (maintainers and forks)

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

Without prebuilt APKs in the image the backend builds them itself at first start (installs a JDK, downloads the build tools, keeps keystores in `data/keys/`). No Gradle or Android SDK is used, see [`backend/android/README.md`](backend/android/README.md).

## Project layout

| Path | What |
|---|---|
| `backend/app/` | Python backend (aiohttp), web UI in `static/` |
| `backend/android/helper/` | helper app for the TV |
| `backend/android/phone/` | phone app (WebView wrapper with QR pairing) |
| `backend/android/build.py` | APK build without Gradle |
| `docker-compose.yml` | ready-to-use Compose file |

## License

[Apache-2.0](LICENSE). The phone app bundles [jsQR](https://github.com/cozmo/jsQR) (Apache-2.0), see `backend/android/phone/assets/THIRD_PARTY.txt`. Homemote is not affiliated with Google; Google TV and Android TV are trademarks of Google LLC.
