# Mochila

Herramienta familiar y privada para descargar material educativo que el usuario tiene derecho a utilizar offline.

## Qué incluye

- API FastAPI y una interfaz web pequeña en HTML/CSS/JS vanilla.
- Sesiones aleatorias almacenadas en Redis durante 30 días.
- Contraseña configurable mediante `APP_PASSWORD`; nunca se envía al navegador.
- Cola Redis y worker dedicado con yt-dlp, FFmpeg y Deno.
- Tickets de descarga de un solo uso y vigencia de 60 segundos.
- Solo URLs de YouTube; las playlists están desactivadas.
- Redis no se publica y la aplicación solo escucha en `127.0.0.1:8080`.

## Arranque local

```bash
cp .env.example .env
```

Edita `.env` y define la contraseña familiar:

```dotenv
APP_PASSWORD=...
```

Después inicia Mochila:

```bash
docker compose up -d --build
docker compose logs -f worker
```

Abre [http://127.0.0.1:8080](http://127.0.0.1:8080):

```text
abrir Mochila
→ poner contraseña una vez
→ cookie persistente durante 30 días
→ pegar URL
→ descargar
```

La cookie de sesión es HttpOnly, SameSite=Lax y, por defecto, funciona sobre HTTP local. Para producción HTTPS, activa:

```dotenv
SESSION_COOKIE_SECURE=true
```

La app aplica un límite básico de 8 intentos de inicio de sesión por IP cada 60 segundos.

## Publicación opcional por IP

El despliegue puede publicarse con HTTPS en `https://IP_DEL_SERVIDOR` usando el proxy Nginx incluido y un certificado de IP de corta duración. Para activar esta modalidad se necesitan los puertos 80 y 443 y una renovación automática frecuente:

```bash
docker compose up -d api worker redis
docker run --rm -p 80:80 \
  -v "$PWD/certbot:/etc/letsencrypt" \
  certbot/certbot:latest certonly --standalone \
  --cert-name mochila-ip --ip-address IP_DEL_SERVIDOR \
  --preferred-profile shortlived \
  --register-unsafely-without-email --agree-tos --non-interactive
docker compose up -d proxy
```

Activa `SESSION_COOKIE_SECURE=true` en `.env` cuando el proxy HTTPS esté funcionando. Los certificados de IP son de corta duración y deben renovarse automáticamente; el script `deploy/renew-ip-cert.sh` detiene temporalmente el proxy durante la renovación y lo vuelve a iniciar después.

## API para scripts

El flujo de scripts usa la misma sesión de cookie que la interfaz:

```bash
curl -c cookies.txt http://127.0.0.1:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password":"TU_APP_PASSWORD"}'
```

Crear un trabajo:

```bash
curl -b cookies.txt -sS http://127.0.0.1:8080/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "url":"https://www.youtube.com/watch?v=VIDEO_ID",
    "mode":"video",
    "max_height":1080
  }'
```

Comprobar sesión y cerrar sesión:

```bash
curl -b cookies.txt http://127.0.0.1:8080/auth/me
curl -b cookies.txt -X POST http://127.0.0.1:8080/auth/logout
```

## Límites actuales

Mochila no descarga playlists, no acepta extractores arbitrarios, no monta cookies de cuentas, no cancela un proceso en ejecución y no expone ingreso público a Internet. Usa el servicio únicamente con material propio o autorizado.

Para contenido privado o restringido por edad, el soporte de cookies debe añadirse más adelante como una funcionalidad explícita de secretos montados; nunca se deben enviar cookies mediante la interfaz.

## Tests

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

## Siguientes mejoras

1. Progreso de descarga mediante hooks de yt-dlp.
2. Cancelación y heartbeats del worker.
3. Cuota de disco y límite de tamaño a nivel de filesystem.
4. Métricas estructuradas y Prometheus.
