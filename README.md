# grafana-live-playground

A small Docker Compose playground for [Grafana Live](https://grafana.com/docs/grafana/latest/setup-grafana/set-up-grafana-live/).
Two data generators push the same sample data to Grafana every 200 ms, one over HTTP and one over WebSocket.
Each has its own dashboard with 17 panels, one for each visualization type that can show a data stream.

| Dashboard | Push method | Channels |
|---|---|---|
| <http://localhost:3000/d/live-http> | HTTP push (`POST /api/live/push/http`) | `stream/http/<measurement>` |
| <http://localhost:3000/d/live-ws> | WebSocket push (`/api/live/push/ws`) | `stream/ws/<measurement>` |

> Unofficial personal project. It is not affiliated with or endorsed by Grafana Labs.

## Quick start

```sh
docker compose up -d --build
```

Open <http://localhost:3000/d/live-http> and log in with `admin` / `admin`.
Grafana may ask you to change the password. You can skip it.

When you are done, remove the containers and volumes:

```sh
docker compose down -v
```

## What is running

| Service | Role |
|---|---|
| `grafana` (`grafana/grafana:13.2.3`) | Grafana with the two dashboards provisioned |
| `generator-http` | Creates sample data every 200 ms and sends it with HTTP push to stream `http` |
| `generator-ws` | Creates the same kind of data and sends it over one WebSocket connection to stream `ws` |

There is no database. Grafana Live keeps only a short buffer of recent data in memory,
so a dashboard starts empty when you open it and fills as new data arrives.

## How data is pushed

Both generators send [InfluxDB line protocol](https://docs.influxdata.com/influxdb/v2/reference/syntax/line-protocol/)
with a nanosecond timestamp:

```
cpu,host=web-1 usage=63.12 1790835940426825000
```

- **HTTP push** is the documented way. The generator sends one `POST` per tick, and the body has all the lines of that tick.
  Any client can do this. Telegraf is not required.
- **WebSocket push** uses the same path, `/api/live/push/<streamId>`, with a WebSocket connection.
  It is not described on the Grafana Live documentation page, but it works with Grafana 13.2.3 in this playground.
  The generator sends one message per line.
- The streamId and the measurement name decide the channel: `stream/<streamId>/<measurement>`.
  Tags become labels, and string fields are kept as strings.
- Panels use the built-in **-- Grafana --** data source with `queryType: "measurements"` and a `channel`.
  The browser receives new frames through Grafana's own WebSocket (`/api/live/ws`), so there is no polling.

| Measurement | Data |
|---|---|
| `cpu` | `usage` for 3 hosts (`host` tag) |
| `ohlc` | open, high, low, close and volume, one candle per tick |
| `geo` | `lat` and `lon` of 3 moving vehicles (`vehicle` tag) |
| `applog` | log lines (`body`, `host` and `level` string fields, no tags), about 2 per second |
| `trend` | `altitude` against a numeric `distance` |
| `sensor` | `temperature` and `humidity` |

## Panels

Both dashboards have the same panels, in the order of the "All visualizations" list in Grafana's panel picker.
Most panels use `cpu`. Five panels have their own measurement because they need a specific data shape.

| # | Visualization | Measurement | Note |
|---|---|---|---|
| 1 | Time series | `cpu` | |
| 2 | Bar chart | `cpu` | |
| 3 | Stat | `cpu` | |
| 4 | Gauge | `cpu` | |
| 5 | Bar gauge | `cpu` | |
| 6 | Table | `cpu` | |
| 7 | Pie chart | `cpu` | |
| 8 | State timeline | `cpu` | |
| 9 | Heatmap | `cpu` | |
| 10 | Status history | `cpu` | |
| 11 | Histogram | `cpu` | |
| 12 | Candlestick | `ohlc` | Needs open, high, low and close fields |
| 13 | Canvas | `cpu` | Wind turbine speed follows `usage` |
| 14 | Geomap | `geo` | Needs latitude and longitude fields |
| 15 | Logs | `applog` | Needs a string field for the log text |
| 16 | Trend | `trend` | Needs a numeric X axis instead of time |
| 17 | XY chart | `sensor` | Needs two numeric fields |

Node graph, Traces and Flame graph are not included. They need their own data formats, which line protocol cannot produce.

## Notes and limits

- **Tested with Grafana 13.2.3.** Every panel has `pluginVersion: "13.2.3"`. Without it, Grafana treats a
  provisioned panel as an old one and runs a migration that can empty it (this happened with the XY chart).
  If you change the Grafana image, update the image tag and `pluginVersion` together, and check the panels again.
- **200 ms interval.** Set `INTERVAL_MS` in `docker-compose.yml` to change it. Both dashboards open 6 Live channels each.
  If the browser feels slow, increase the interval or open only one dashboard.
- **Millisecond precision.** The generator sends nanosecond timestamps, but Grafana's data frames and the browser
  work in milliseconds. Do not expect to see finer differences on screen.
- **Trend** needs a strictly ascending X value. The generator counts `distance` from a fixed epoch, so it keeps
  rising when you restart a generator.
- **Geomap** loads its map tiles from the internet in your browser. Without a connection you only see the markers.
- **Canvas** is the most experimental panel. It shows a wind turbine whose speed (RPM) is bound to the `usage` field,
  so a higher CPU usage spins the blades faster. A value box next to it shows the number.
- **Password changes.** Grafana reads `GF_SECURITY_ADMIN_PASSWORD` only when it creates its database.
  If you change the password later, run `docker compose down -v` first, or use `grafana cli admin reset-admin-password`.
  The generators use the same password to push to Grafana Live. You can set `GRAFANA_PASSWORD` in a `.env` file
  (it is ignored by git).

## Files

```
docker-compose.yml                         Grafana and the two generators
generator/                                 Sample data generator (Python, websockets)
grafana/provisioning/dashboards/           Dashboard provider
grafana/dashboards/live-http.json          Dashboard for HTTP push
grafana/dashboards/live-ws.json            Dashboard for WebSocket push
```
