"""Generate sample data and push it to Grafana Live every INTERVAL_MS (default 200 ms).

PUSH_MODE=http : POST InfluxDB line protocol to /api/live/push/<STREAM_ID>
PUSH_MODE=ws   : send the same lines over a WebSocket to /api/live/push/<STREAM_ID>

Each measurement becomes a channel: stream/<STREAM_ID>/<measurement>
"""
import asyncio
import base64
import math
import os
import random
import time
import urllib.error
import urllib.request

import websockets

MODE = os.environ["PUSH_MODE"]
STREAM_ID = os.environ["STREAM_ID"]
INTERVAL = int(os.environ.get("INTERVAL_MS", "200")) / 1000
GRAFANA_URL = os.environ["GRAFANA_URL"]
AUTH = "Basic " + base64.b64encode(
    f"{os.environ['GRAFANA_USER']}:{os.environ['GRAFANA_PASSWORD']}".encode()
).decode()

HOSTS = ["web-1", "web-2", "web-3"]
LOG_EVENTS = [
    ("info", "request completed status=200"),
    ("info", "cache hit ratio=0.93"),
    ("warn", "slow query took 850ms"),
    ("error", "upstream connection refused"),
]

# Trend needs a strictly ascending X. Counting from a fixed epoch (not from process
# start) keeps it ascending even when the generator restarts.
TREND_EPOCH = 1790812800

_price = {"close": 100.0}
_push_failing = False


def make_lines(ts: int, t: float) -> list[str]:
    """Build one tick of line protocol. ts is in nanoseconds, t is seconds since start."""
    lines = [
        f"cpu,host={h} usage={50 + 40 * math.sin(t / 10 + i) + random.uniform(-5, 5):.2f} {ts}"
        for i, h in enumerate(HOSTS)
    ]

    temp = 22 + 3 * math.sin(t / 30) + random.uniform(-0.3, 0.3)
    humidity = 55 + 10 * math.cos(t / 45) + random.uniform(-1, 1)
    lines.append(f"sensor,room=lab temperature={temp:.2f},humidity={humidity:.2f} {ts}")

    # One candle per tick: random walk, open = previous close.
    o = _price["close"]
    c = o + random.uniform(-0.6, 0.6)
    h = max(o, c) + random.uniform(0, 0.3)
    low = min(o, c) - random.uniform(0, 0.3)
    _price["close"] = c
    lines.append(
        f"ohlc,symbol=DEMO open={o:.2f},high={h:.2f},low={low:.2f},close={c:.2f},"
        f"volume={random.randint(100, 1000)}i {ts}"
    )

    # Three vehicles circling around Tokyo station (lat 35.681, lon 139.767).
    lines += [
        f"geo,vehicle=car-{i} "
        f"lat={35.681 + 0.02 * (i + 1) * math.sin(t / 20 + i * 2):.5f},"
        f"lon={139.767 + 0.02 * (i + 1) * math.cos(t / 20 + i * 2):.5f} {ts}"
        for i in range(3)
    ]

    # Numeric X axis (distance) instead of time, for the Trend panel.
    distance = ts / 1e9 - TREND_EPOCH
    altitude = 100 + 30 * math.sin(t / 15) + random.uniform(-2, 2)
    lines.append(f"trend,route=a distance={distance:.3f},altitude={altitude:.2f} {ts}")

    # About 2 log lines per second on average. host, level and body are all string
    # fields and there are no tags. Grafana Live makes one column per tag combination,
    # so tags would spread the log lines over many columns and leave empty messages.
    # The values have no double quotes inside.
    if random.random() < 0.4:
        level, msg = random.choices(LOG_EVENTS, weights=[6, 4, 2, 1])[0]
        lines.append(f'applog host="{random.choice(HOSTS)}",level="{level}",body="{msg}" {ts}')

    return lines


def post(url: str, body: str) -> None:
    global _push_failing
    req = urllib.request.Request(
        url,
        data=body.encode(),
        headers={"Authorization": AUTH, "Content-Type": "text/plain"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5).close()
        _push_failing = False
    except (urllib.error.URLError, OSError) as e:
        # Print once per failure streak, not every tick.
        if not _push_failing:
            print(f"POST {url} failed: {e}")
        _push_failing = True


async def run_every(interval: float, tick) -> None:
    """Call tick() every interval seconds without drifting. If a tick runs late, skip the backlog."""
    next_at = time.monotonic()
    while True:
        await tick()
        next_at += interval
        delay = next_at - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        else:
            next_at = time.monotonic()


async def http_loop(t0: float) -> None:
    url = f"{GRAFANA_URL}/api/live/push/{STREAM_ID}"

    async def tick() -> None:
        body = "\n".join(make_lines(time.time_ns(), time.time() - t0))
        await asyncio.to_thread(post, url, body)

    await run_every(INTERVAL, tick)


async def ws_loop(t0: float) -> None:
    # Reconnect forever: Grafana may not be ready when the container starts.
    ws_url = GRAFANA_URL.replace("http", "ws", 1) + f"/api/live/push/{STREAM_ID}"
    while True:
        try:
            async with websockets.connect(ws_url, additional_headers={"Authorization": AUTH}) as ws:
                print("WebSocket connected:", ws_url)

                async def tick() -> None:
                    # One message per line. Sending several lines in one message
                    # is not documented, so keep it simple and safe.
                    for line in make_lines(time.time_ns(), time.time() - t0):
                        await ws.send(line)

                await run_every(INTERVAL, tick)
        except Exception as e:  # noqa: BLE001 - demo script, just retry
            print(f"WebSocket error: {e}; retrying in 3s")
            await asyncio.sleep(3)


async def main() -> None:
    t0 = time.time()
    print(f"mode={MODE} stream={STREAM_ID} interval={INTERVAL * 1000:.0f}ms")
    await (http_loop(t0) if MODE == "http" else ws_loop(t0))


asyncio.run(main())
