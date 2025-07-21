# server.py – tiny aiohttp server for the calendar bot
# /                shows a simple HTML page with instructions
# /cal/{id}.ics    serves the raw .ics for that Discord user ID

import datetime as dt
import logging
from urllib.parse import urlparse

import aiohttp.web

from config import BASE_URL, HTTP_PORT, POLL_INTERVAL
from file_helpers import ics_path

log = logging.getLogger(__name__)
app = aiohttp.web.Application()

# you’ll see this host in the homepage input box
HOST = urlparse(BASE_URL).netloc

# homepage


async def handle_home(request):
    html = f"""<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width,initial-scale=1'>
  <title>Discord Events Calendar</title>
  <style>
    body {{font-family:'Segoe UI',Tahoma,sans-serif;background:#eef2f7;margin:0}}
    .container {{max-width:720px;margin:40px auto;background:#fff;padding:30px;box-shadow:0 4px 12px rgba(0,0,0,.1);border-radius:10px}}
    .input-group {{margin:20px 0;display:flex}}
    .input-group input {{flex:1;padding:10px;border:1px solid #ccc;border-right:0;border-radius:4px 0 0 4px;font-size:1em}}
    .input-group button {{padding:10px 20px;border:0;background:#1d72b8;color:#fff;border-radius:0 4px 4px 0;cursor:pointer}}
    .input-group button:hover {{background:#155d8b}}
    .footer {{margin-top:30px;font-size:.9em;color:#777}}
  </style>
</head>
<body>
  <div class='container'>
    <h1>Discord Events Calendar</h1>
    <p>Subscribe to your personal calendar feed and stay up to date automatically.</p>
    <p>Replace <code>{{YOUR_DISCORD_USER_ID}}</code> in the URL below:</p>
    <div class='input-group'>
      <input value='webcal://{HOST}/cal/{{YOUR_DISCORD_USER_ID}}.ics' readonly onclick='this.select();document.execCommand("copy");'>
      <button onclick='navigator.clipboard.writeText("webcal://{HOST}/cal/{{YOUR_DISCORD_USER_ID}}.ics");alert("Copied");'>Copy</button>
    </div>
    <div class='footer'>© {dt.datetime.now().year} Bot · auto‑refresh every {POLL_INTERVAL} min</div>
  </div>
</body>
</html>"""
    return aiohttp.web.Response(text=html, content_type="text/html")


# serve the .ics file


async def handle_feed(request):
    try:
        uid = int(request.match_info["id"])
    except (KeyError, ValueError):
        raise aiohttp.web.HTTPNotFound()

    path = ics_path(uid)
    if not path.exists():
        raise aiohttp.web.HTTPNotFound()

    return aiohttp.web.FileResponse(
        path,
        headers={
            "Content-Type": "text/calendar; charset=utf-8",
            "Content-Disposition": f'inline; filename="{uid}.ics"',
            "Content-Encoding": "identity",
        },
    )


# route table
app.router.add_get("/", handle_home)
app.router.add_get("/cal/{id}.ics", handle_feed)

# run the server


async def run_http():
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    log.info("HTTP server running on port %s", HTTP_PORT)
