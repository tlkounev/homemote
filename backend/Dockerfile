FROM python:3.12-slim

# Android platform-tools (adb) – jen pro jednorázovou instalaci helperu na TV.
# Binárka je pro x86_64 (image je linux/amd64).
ADD https://dl.google.com/android/repository/platform-tools-latest-linux.zip /tmp/pt.zip
RUN python -c "import zipfile; zipfile.ZipFile('/tmp/pt.zip').extractall('/opt')" \
 && chmod +x /opt/platform-tools/adb && rm /tmp/pt.zip
ENV PATH="/opt/platform-tools:${PATH}"

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY android ./android
# Hotová APK (pomocník, aplikace pro telefon) – v CI je sem nakopíruje workflow release.yml.
# Při lokálním sestavení je složka prázdná a backend si APK sestaví sám při startu (doinstaluje JDK).
COPY apk-dist/ /opt/homemote/apk/

# /data: stav, certifikát pro párování, ADB klíče (HOME); bez hotových APK v image i sestavená APK + klíče (keys/)
ENV DATA_DIR=/data HOME=/data/home PORT=888 PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 888
CMD ["python", "-m", "app.main"]
