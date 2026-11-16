import asyncio
import re
import time

import requests
from aiohttp import web
from server import PromptServer

from . import keys

API_URL = "https://openrouter.ai/api/v1"
HEADERS = {"HTTP-Referer": "https://maybaum.ch", "X-Title": "Maybaum Custom Nodes"}

# kind ("images" | "videos") -> (load time, {model_id: model entry from /{kind}/models})
_models = {}
MODELS_TTL = 10 * 60
# model_id -> (load time, endpoints with prices) for image models. Video prices are in the model list itself.
_endpoints = {}
# Output formats that decode to IMAGE. Not SVG.
RASTER_FORMATS = ("png", "jpeg", "webp")


def request(alias, method, path, timeout=600, **kwargs):
    res = requests.request(method, API_URL + path, headers={**HEADERS, "Authorization": f"Bearer {keys.get(alias, 'openrouter')}"}, timeout=timeout, **kwargs)
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
        # Keep using the old list while OpenRouter is unreachable.
        if models is not None:
            return models
        raise
    _models[kind] = (time.time(), {m["id"]: m for m in res.json()["data"]})
    return _models[kind][1]


def image_params(model):
    return _load_models("images").get(model, {}).get("supported_parameters") or {}


def transparent_format(model):
    """None if the model cannot do a transparent background. Otherwise the alpha-capable output
    format that must be sent along, or "" if the model has no output_format."""
    params = image_params(model)
    if "transparent" not in (params.get("background") or {}).get("values", []):
        return None
    formats = (params.get("output_format") or {}).get("values")
    if formats is None:
        return ""
    return next((f for f in ("png", "webp") if f in formats), None)


def _choices(values, allowed=None):
    """Selectable values without "auto". None if there is nothing to choose."""
    values = [str(v) for v in values or [] if v != "auto" and (allowed is None or v in allowed)]
    return values if len(values) > 1 else None


def capabilities(kind, model):
    """What the model lets you set, by widget name.
    list = dropdown values, number = maximum, True = toggle."""
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
    """Checks widget values against the model. "auto", batch 1 and False are neutral."""
    try:
        models = _load_models(kind)
    except requests.RequestException as e:
        return f"Could not load model list from OpenRouter: {type(e).__name__}"
    if model not in models:
        return f"Model '{model}' is not available on OpenRouter."
    caps = capabilities(kind, model)
    for name, value in values.items():
        if name == "batch":
            if not 1 <= value <= caps.get("batch", 1):
                return f"batch {value}: model '{model}' allows 1 to {caps.get('batch', 1)}."
        elif isinstance(value, bool):
            if value and name not in caps:
                return f"{name}: model '{model}' does not support this."
        elif value != "auto" and value not in caps.get(name, []):
            allowed = ", ".join(["auto", *caps.get(name, [])])
            return f"{name} '{value}' is not possible with model '{model}'. Allowed: {allowed}."
    return True


def _load_endpoints(model):
    loaded, endpoints = _endpoints.get(model, (0, None))
    if endpoints is not None and time.time() - loaded < MODELS_TTL:
        return endpoints
    res = requests.get(f"{API_URL}/images/models/{model}/endpoints", headers=HEADERS, timeout=15)
    res.raise_for_status()
    _endpoints[model] = (time.time(), res.json()["endpoints"])
    return _endpoints[model][1]


def _prefer(items, *keeps):
    """Narrows down filter by filter. A filter without matches is skipped."""
    for keep in keeps:
        items = [i for i in items if keep(i)] or items
    return items


def _usd(value):
    return f"${value:.3f}" if value < 0.1 else f"${value:.2f}"


def _span(prices, suffix=""):
    low, high = min(prices), max(prices)
    if high - low < 0.0005:
        return _usd(low) + suffix
    return f"{_usd(low)}-{_usd(high)[1:]}{suffix}"


def _image_estimate(model, resolution, quality, batch, references):
    totals, extras, others = [], [], set()
    for endpoint in _load_endpoints(model):
        pricing = endpoint.get("pricing") or []
        outputs = [p for p in pricing if p["billable"] == "output_image" and p["unit"] == "image"]
        # variant: None = base price, "2k" or "low_2k" = resolution (with quality). Ignore surcharges like "moodboards".
        sized = [p for p in outputs if p.get("variant") and re.fullmatch(r"(\w+_)?(768|[\d.]+k)", p["variant"])]
        base = [p for p in outputs if not p.get("variant")]
        if quality != "auto":
            sized = _prefer(sized, lambda p: p["variant"].startswith(quality + "_"))
        if resolution != "auto":
            chosen = [p for p in sized if p["variant"].split("_")[-1] == resolution.lower()] or base
        else:
            chosen = base or sized
        if chosen:
            totals.append([p["cost_usd"] * batch for p in chosen])
            per_reference = sum(p["cost_usd"] for p in pricing if p["billable"] in ("input_image", "input_reference") and p["unit"] == "image" and not p.get("variant"))
            extras.append(per_reference * references)
            continue
        for p in pricing:
            if p["billable"] == "output_image" and p["unit"] == "megapixel":
                others.add(f"{_usd(p['cost_usd'])}/megapixel")
            elif p["billable"] == "output_image" and p["unit"] == "token":
                others.add("Token pricing, cost known after run")
    if totals:
        return "~" + _span([t + e for prices, e in zip(totals, extras) for t in prices])
    return " · ".join(sorted(others))


def _video_estimate(model, duration, resolution, generate_audio, frames, references):
    entry = _load_models("videos").get(model, {})
    rates = []
    image_input = 0.0
    minimum = 0.0
    for key, value in (entry.get("pricing_skus") or {}).items():
        usd = float(value) / (100 if "cents" in key else 1)
        if key in ("cents_per_image_input", "reference_images", "reference_input_images"):
            image_input += usd
        elif key == "minimum_cents_per_generation":
            minimum = usd
        elif match := re.fullmatch(r"(?:(text_to_video|image_to_video)_)?(?:duration_seconds|cents_per_second_output|cents_per_video_output_second)(?:_(with_audio|without_audio))?(?:_(\d+p|\d+k))?", key):
            mode, audio, res = match.groups()
            rates.append({"usd": usd, "mode": mode, "audio": audio, "res": res})
    if not rates:
        if any(k.startswith("video_tokens") for k in entry.get("pricing_skus") or {}):
            return "Video token pricing, cost known after run"
        return ""
    if resolution != "auto":
        rates = _prefer(rates, lambda r: r["res"] == resolution.lower(), lambda r: r["res"] is None)
    else:
        rates = _prefer(rates, lambda r: r["res"] is None)
    if entry.get("generate_audio") and generate_audio:
        rates = _prefer(rates, lambda r: r["audio"] == "with_audio", lambda r: r["audio"] is None)
    else:
        rates = _prefer(rates, lambda r: r["audio"] == "without_audio", lambda r: r["audio"] is None)
    rates = _prefer(rates, lambda r: r["mode"] == ("image_to_video" if frames else "text_to_video"), lambda r: r["mode"] is None)
    extra = image_input * (frames + references)
    if duration == "auto":
        return _span([r["usd"] for r in rates], "/s") + " · duration auto"
    return "~" + _span([max(r["usd"] * int(duration) + extra, minimum) for r in rates])


def estimate(kind, model, values):
    """Cost estimate per run as text, empty if OpenRouter has no prices."""
    if kind == "images":
        return _image_estimate(model, values["resolution"], values["quality"], int(values["batch"]), int(values["references"]))
    return _video_estimate(model, values["duration"], values["resolution"], values["generate_audio"], int(values["frames"]), int(values["references"]))


routes = PromptServer.instance.routes


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


@routes.post("/maybaum/openrouter/estimate/{kind}")
async def get_estimate(request):
    kind = request.match_info["kind"]
    if kind not in ("images", "videos"):
        raise web.HTTPNotFound()
    data = await request.json()
    try:
        text = await asyncio.to_thread(estimate, kind, data["model"], data["values"])
    except requests.RequestException:
        text = ""
    return web.json_response({"text": text})
