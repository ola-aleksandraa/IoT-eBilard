# Website backend

FastAPI service behind the web application. It provides configuration and
numerical shot planning on normalized ball layouts. Ball recognition (camera
capture and analysis) runs on the Raspberry Pi service,
[back_raspberry/](../back_raspberry/README.md).

## Start

Python **3.11–3.13** and [uv](https://docs.astral.sh/uv/) are required.

```sh
cd back_website
uv sync --python 3.12 --frozen
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8001
```

From the repository root, `pnpm dev` starts this backend together with the
frontend dev server, which proxies `/api` to port 8001.

- Interactive docs: **[http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)**
- Machine-readable contract: [http://127.0.0.1:8001/openapi.json](http://127.0.0.1:8001/openapi.json)
- Process health: [http://127.0.0.1:8001/health](http://127.0.0.1:8001/health)

## Public API

| Method and path | Input | Numerical response |
| --- | --- | --- |
| `GET /health` | — | `status`, `service`, `version` |
| `GET /api/v1/settings` | — | Default per-frame detector settings |
| `GET /api/v1/categories` | — | `cue`, `eight`, `solid`, `striped`, `unknown` and meanings |
| `POST /api/v1/shots` | Normalized ball layout | Ranked direct/bank shot paths and scores |
| `POST /api/v1/shots/predict` | Layout and cue aim | First contact and pocket paths |
| `POST /api/v1/shots/simulate` | Layout, cue aim and power | Time-sampled ball motion, contacts, cushions and pots |

`/settings` returns the defaults of the `settings` object accepted by the Pi's
camera routes. The model is duplicated in [app/schemas.py](app/schemas.py);
keep it in sync with `Settings` in `back_raspberry/app/engine/models.py`.

## Shot requests

Shot routes accept at most 24 balls with unique layout-local IDs. Each ball needs
only `id`, `kind`, `x`, `y`, `radius`; extra detection evidence is ignored, so
`detection.balls` from the Pi's `/camera/detect` can be sent unchanged together
with `detection.geometry.table_ratio`. Coordinates are normalized to the cloth:
`x`, `y` in `[0,1]`, origin top-left, y down, `radius` relative to table height.
`/shots` also accepts `top_n` (1–20), `include_bank` and `include_blocked`. Aim
operations accept `aim_x`, `aim_y` in [0,1]; simulation adds `power` in [0,1].
All three share one admission guard and return `503` with `Retry-After: 1` while
another operation is active.

```sh
curl -sS http://127.0.0.1:8001/api/v1/shots/simulate \
  -H 'Content-Type: application/json' \
  -d '{"balls":[{"id":1,"kind":"cue","x":0.2,"y":0.5,"radius":0.026},{"id":2,"kind":"solid","x":0.6,"y":0.5,"radius":0.026}],"aim_x":0.9,"aim_y":0.5,"power":0.6}'
```

Results describe hypothetical motion using the original PoC physics assumptions,
not a calibrated forecast for the physical table. They contain coordinates and
events only, without pixels or rendering styles.

## Structure

```text
app/
  main.py                 Application factory, health and docs
  schemas.py              Configuration and shot contracts
  api/routes.py           Configuration and shot routes
  api/dependencies.py     Shared admission control
  trajectory/             Numerical shot planning and motion simulation
```

## Tests

```sh
uv run --frozen pytest -q
```
