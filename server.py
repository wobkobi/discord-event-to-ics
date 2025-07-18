# server.py
# ----------------
import logging
import datetime as dt
import aiohttp.web
from urllib.parse import urlparse

from config import HTTP_PORT, BASE_URL, POLL_INTERVAL
from file_helpers import ics_path

log = logging.getLogger(__name__)
app = aiohttp.web.Application()

# parse HOST once for homepage webcal link
parsed = urlparse(BASE_URL)
host = parsed.netloc


async def handle_home(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Serve styled HTML homepage with subscription instructions, offering a webcal link."""
    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\"/>
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"/>
  <title>Discord Events Calendar</title>
  <style>
    body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background: #eef2f7; margin:0; padding:0; }}
    .container {{ max-width: 720px; margin: 40px auto; background: #fff; padding: 30px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.1); border-radius: 10px; }}
    h1 {{ color: #333; margin-bottom: 10px; }}
    p {{ color: #555; line-height: 1.6; }}
    code {{ background: #f1f1f1; padding: 2px 4px; border-radius:4px; font-size:0.95em; }}
    .input-group {{ margin: 20px 0; display: flex; }}
    .input-group input {{ flex:1; padding:10px; font-size:1em; border:1px solid #ccc; border-radius:4px 0 0 4px; }}
    .input-group button {{ padding:10px 20px; font-size:1em; border:none; background:#1d72b8; color:#fff; cursor:pointer; border-radius:0 4px 4px 0; }}
    .input-group button:hover {{ background:#155d8b; }}
    .footer {{ margin-top:30px; font-size:0.9em; color:#777; }}
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>Discord Events Calendar</h1>
    <p>Subscribe to your personal calendar feed and stay up-to-date automatically.</p>
    <p>Use the URL below, replacing <code>{'{id}'}</code> with your Discord ID:</p>
    <div class=\"input-group\">
      <input type=\"text\" readonly
             value=\"webcal://{host}/cal/{{YOUR_DISCORD_USER_ID}}.ics\"
             onclick=\"this.select(); document.execCommand('copy');\" />
      <button onclick=\"navigator.clipboard.writeText('webcal://{host}/cal/{{YOUR_DISCORD_USER_ID}}.ics');alert('Copied');\">Copy</button>
    </div>
    <div class=\"footer\">&copy; {dt.datetime.now().year} Bot. Auto-refresh every {POLL_INTERVAL} min.</div>
  </div>
</body>
</html>"""
    return aiohttp.web.Response(text=html, content_type="text/html")


async def handle_feed(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
    """
    Serve the ICS feed file for a given user ID, with RFC-5545 headers.
    """
    try:
        uid = int(request.match_info["id"])
    except (KeyError, ValueError):
        raise aiohttp.web.HTTPNotFound()

    path = ics_path(uid)
    if not path.exists():
        raise aiohttp.web.HTTPNotFound()

    # Stream the file with calendar-specific headers
    return aiohttp.web.FileResponse(
        path=path,
        headers={
            "Content-Type": "text/calendar; charset=utf-8",
            # Disposition makes Apple / Outlook happier on first import
            "Content-Disposition": f'inline; filename="{uid}.ics"',
            # Disable compression “on the wire” if an ISP or proxy mangles it
            "Content-Encoding": "identity",
        },
    )


# Register routes
app.router.add_get("/", handle_home)
app.router.add_get("/cal/{id}.ics", handle_feed)


async def run_http() -> None:
    """Start the aiohttp server on the configured port."""
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    log.info(f"HTTP server running on port {HTTP_PORT}")
