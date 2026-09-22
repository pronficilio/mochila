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

## Residential YouTube egress

Mochila, FastAPI, Redis, el worker, yt-dlp, FFmpeg y los archivos finales siguen
viviendo en Hetzner. De forma opcional, **solo** las conexiones que yt-dlp hace a
YouTube pueden salir por un proxy SOCKS5 de una red residencial. El resto del
tráfico del servidor y de los contenedores continúa saliendo normalmente.

La infraestructura Tailscale y el servidor SOCKS residencial están documentados
paso a paso en [docs/residential-egress.md](docs/residential-egress.md). El host de
Hetzner y, por tanto, el contenedor `worker`, deben poder alcanzar el listener SOCKS
residencial (por ejemplo, `100.x.x.x:1080`). No se instala Tailscale dentro de los
contenedores.

Para activarlo, edita `.env`:

```dotenv
DOWNLOAD_EGRESS=residential
RESIDENTIAL_PROXY=socks5://100.64.0.10:1080
```

El modo residencial usa `socks5://` y añade `--force-ipv4` a yt-dlp. Mochila usa un
wrapper pequeño para preservar la resolución SOCKS5 local de IPv4: los nombres se
resuelven en el worker y las conexiones TCP y descargas salen por el SOCKS
residencial. Si el SOCKS exige
autenticación, usa únicamente la variable de entorno, por ejemplo
`socks5://usuario:contraseña@100.64.0.10:1080`; no la compartas ni la incluyas en
el repositorio. Mochila no escribe las credenciales del proxy en logs ni en errores.

Recrea los servicios tras cambiar `.env`:

```bash
docker compose up -d --build
```

Comprueba la conectividad desde el worker sin revelar la URL ni sus credenciales:

```bash
docker compose exec worker python -c 'from app.downloader import residential_proxy_reachable; print("reachable" if residential_proxy_reachable() else "unreachable")'
```

Con una sesión de Mochila también puedes consultar el estado del egress. El
endpoint no devuelve host, IP ni credenciales del proxy:

```bash
curl -b cookies.txt -sS http://127.0.0.1:8080/v1/egress
```

En modo residencial, un proxy inaccesible hace que el trabajo falle rápidamente
con `Residential egress is unavailable`. No existe fallback automático a salida
directa: de ese modo la IP de Hetzner nunca se usa por accidente para una descarga.

Para regresar al comportamiento habitual:

```dotenv
DOWNLOAD_EGRESS=direct
RESIDENTIAL_PROXY=
```

Las configuraciones residenciales sin `RESIDENTIAL_PROXY`, o con un esquema distinto
de `socks5://`, impiden que el servicio inicie.

### PO Tokens automáticos para YouTube

En modo residencial Mochila ejecuta el cliente `mweb` de yt-dlp y solicita los PO
Tokens GVS necesarios a `bgutil-ytdlp-pot-provider`. Es un provider automático: no
usa una cuenta Google, cookies de cuenta, cookies exportadas ni tokens pegados a
mano. El plugin de Python y el servidor HTTP privado se fijan ambos a la versión
`2.0.0` para que el despliegue sea reproducible.

El servicio `pot-provider` solo vive en la red interna de Docker: no tiene puertos
publicados. yt-dlp recibe estos argumentos efectivos únicamente en modo
`residential`:

```text
--force-ipv4
--proxy socks5://TAILSCALE_HOME_IP:1080
--extractor-args youtube:player_client=mweb;fetch_pot=auto
--extractor-args youtubepot-bgutilhttp:base_url=http://pot-provider:4416
```

El provider recibe el SOCKS configurado desde el plugin, por lo que sus peticiones
para generar el token salen por la misma ruta residencial; no se crea fallback
directo. `YOUTUBE_POT_PROVIDER_URL` debe conservar el valor interno de Compose:

```dotenv
YOUTUBE_POT_PROVIDER_URL=http://pot-provider:4416
```

Para comprobar que está activo sin hacer una petición a YouTube:

```bash
docker compose exec worker python -m app.ytdlp_runner -v --version
docker compose logs --tail=50 pot-provider
```

En una descarga verbose yt-dlp debe listar `bgutil:http-2.0.0 (external)` dentro de
`PO Token Providers` y solicitar un token GVS de `mweb` cuando YouTube lo requiera.
Un HTTP 429 o el mensaje de verificación se registra como `YOUTUBE_RATE_LIMITED`;
Mochila no hace fallback a la IP de Hetzner. Espera antes de volver a probar para no
intensificar un soft block.

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
