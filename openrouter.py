import asyncio
import time

import requests
from aiohttp import web
from server import PromptServer

API_URL = "https://openrouter.ai/api/v1"
HEADERS = {"HTTP-Referer": "https://maybaum.ch", "X-Title": "Maybaum Custom Nodes"}

# Keys leben nur im RAM dieses Prozesses. Nie speichern, nie loggen, nie ausgeben.
_keys = {}
# kind ("images" | "videos") -> (Ladezeit, {model_id: Modelleintrag aus /{kind}/models})
_models = {}
MODELS_TTL = 10 * 60
# Ausgabeformate, die als IMAGE dekodiert werden können. SVG nicht.
RASTER_FORMATS = ("png", "jpeg", "webp")


def check_alias(alias):
    if alias in _keys:
        return True
    return f"Key für Kunde '{alias}' nicht geladen. Auf der Node «OpenRouter API» unter «Keys verwalten» einfügen."


def request(alias, method, path, timeout=600, **kwargs):
    if alias not in _keys:
        raise ValueError(check_alias(alias))
    res = requests.request(method, API_URL + path, headers={**HEADERS, "Authorization": f"Bearer {_keys[alias]}"}, timeout=timeout, **kwargs)
    if not res.ok:
        raise RuntimeError(f"OpenRouter {method} {path} · Status {res.status_code}: {res.text[:500]}")
    return res


def _load_models(kind):
    loaded, models = _models.get(kind, (0, None))
    if models is not None and time.time() - loaded < MODELS_TTL:
        return models
    try:
        res = requests.get(f"{API_URL}/{kind}/models", headers=HEADERS, timeout=15)
        res.raise_for_status()
    except requests.RequestException:
        # Alte Liste weiterverwenden, solange OpenRouter nicht erreichbar ist.
        if models is not None:
            return models
        raise
    _models[kind] = (time.time(), {m["id"]: m for m in res.json()["data"]})
    return _models[kind][1]


def image_params(model):
    return _load_models("images").get(model, {}).get("supported_parameters") or {}


def transparent_format(model):
    """None, wenn das Modell keinen transparenten Hintergrund kann. Sonst das Ausgabeformat
    mit Alpha, das mitgeschickt werden muss, oder "" wenn das Modell output_format nicht kennt."""
    params = image_params(model)
    if "transparent" not in (params.get("background") or {}).get("values", []):
        return None
    formats = (params.get("output_format") or {}).get("values")
    if formats is None:
        return ""
    return next((f for f in ("png", "webp") if f in formats), None)


def _choices(values, allowed=None):
    """Wählbare Werte ohne "auto". None, wenn es nichts zu wählen gibt."""
    values = [str(v) for v in values or [] if v != "auto" and (allowed is None or v in allowed)]
    return values if len(values) > 1 else None


def capabilities(kind, model):
    """Was sich beim Modell einstellen lässt, nach Widget-Name.
    Liste = Dropdown-Werte, Zahl = Maximum, True = Schalter."""
    caps = {}
    if kind == "images":
        params = image_params(model)
        for name in ("aspect_ratio", "resolution", "quality", "output_format"):
            values = _choices((params.get(name) or {}).get("values"), RASTER_FORMATS if name == "output_format" else None)
            if values:
                caps[name] = values
        batch = (params.get("n") or {}).get("max") or 1
        if batch > 1:
            caps["batch"] = batch
        if "seed" in params:
            caps["seed"] = True
        if transparent_format(model) is not None:
            caps["transparent_background"] = True
    else:
        entry = _load_models(kind).get(model, {})
        for name in ("resolution", "aspect_ratio", "duration"):
            values = _choices(entry.get(f"supported_{name}s"))
            if values:
                caps[name] = values
        for name in ("generate_audio", "seed"):
            if entry.get(name):
                caps[name] = True
    return caps


def check_options(kind, model, **values):
    """Prüft Widget-Werte gegen das Modell. Neutral sind "auto", batch 1 und False."""
    try:
        models = _load_models(kind)
    except requests.RequestException as e:
        return f"Modellliste von OpenRouter nicht ladbar: {type(e).__name__}"
    if model not in models:
        return f"Modell '{model}' ist bei OpenRouter nicht verfügbar."
    caps = capabilities(kind, model)
    for name, value in values.items():
        if name == "batch":
            if not 1 <= value <= caps.get("batch", 1):
                return f"batch {value}: Modell '{model}' erlaubt 1 bis {caps.get('batch', 1)}."
        elif isinstance(value, bool):
            if value and name not in caps:
                return f"{name}: Modell '{model}' unterstützt das nicht."
        elif value != "auto" and value not in caps.get(name, []):
            allowed = ", ".join(["auto", *caps.get(name, [])])
            return f"{name} '{value}' ist bei Modell '{model}' nicht möglich. Erlaubt: {allowed}."
    return True


routes = PromptServer.instance.routes


@routes.get("/maybaum/openrouter/aliases")
async def list_aliases(request):
    return web.json_response(sorted(_keys))


@routes.post("/maybaum/openrouter/keys")
async def add_key(request):
    data = await request.json()
    alias = str(data.get("alias", "")).strip()
    key = str(data.get("key", "")).strip()
    if not alias or not key:
        return web.json_response({"error": "Alias und Key angeben."}, status=400)
    res = await asyncio.to_thread(requests.get, f"{API_URL}/key", headers={**HEADERS, "Authorization": f"Bearer {key}"}, timeout=15)
    if not res.ok:
        return web.json_response({"error": f"OpenRouter lehnt den Key ab (Status {res.status_code})."}, status=400)
    _keys[alias] = key
    info = res.json().get("data", {})
    return web.json_response({"alias": alias, "label": info.get("label"), "limit": info.get("limit"), "limit_remaining": info.get("limit_remaining"), "usage": info.get("usage")})


@routes.delete("/maybaum/openrouter/keys/{alias}")
async def delete_key(request):
    _keys.pop(request.match_info["alias"], None)
    return web.json_response(sorted(_keys))


@routes.get("/maybaum/openrouter/models/{kind}")
async def list_models(request):
    kind = request.match_info["kind"]
    if kind not in ("images", "videos"):
        raise web.HTTPNotFound()
    models = await asyncio.to_thread(_load_models, kind)
    return web.json_response(sorted(models))


@routes.get("/maybaum/openrouter/capabilities/{kind}")
async def list_capabilities(request):
    kind = request.match_info["kind"]
    if kind not in ("images", "videos"):
        raise web.HTTPNotFound()
    caps = await asyncio.to_thread(lambda: {m: capabilities(kind, m) for m in _load_models(kind)})
    return web.json_response(caps)
