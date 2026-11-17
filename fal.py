import asyncio
import time

import requests
from aiohttp import web
from server import PromptServer

import comfy.model_management

from . import keys

API_URL = "https://api.fal.ai/v1"
QUEUE_URL = "https://queue.fal.run"
REST_URL = "https://rest.fal.ai"
CDN_URL = "https://v3.fal.media"
# Uploads and results are public URLs on the fal CDN. Let fal delete them after an hour.
LIFECYCLE = '{"expiration_duration_seconds": 3600}'
MODELS_TTL = 10 * 60
JOB_TIMEOUT = 30 * 60

UPSCALE_WORDS = ("upscal", "increase-resolution", "-sr", "esrgan", "vsr")
INPAINT_WORDS = ("inpaint", "fill", "eraser", "object-removal")
# Live search on fal per node, one request per search word. keep() drops search hits that are not this task.
TASKS = {
    "image_upscale": {"q": ("upscale",), "category": "image-to-image", "keep": lambda eid, meta: any(w in f"{eid} {meta['display_name']}".lower() for w in UPSCALE_WORDS)},
    "video_upscale": {"q": ("upscale",), "category": "video-to-video", "keep": lambda eid, meta: any(w in f"{eid} {meta['display_name']}".lower() for w in UPSCALE_WORDS)},
    "video_interpolate": {"q": ("interpolat",), "category": "video-to-video", "keep": lambda eid, meta: True},
    "image_inpaint": {"q": ("inpaint", "fill", "eraser"), "category": "image-to-image", "keep": lambda eid, meta: any(w in eid.lower() for w in INPAINT_WORDS)},
}
# Node widget -> model parameters it fills, first match wins.
PARAMS = {
    "upscale_factor": ("upscale_factor", "scale", "scale_factor"),
    "variant": ("model",),
    "target_resolution": ("target_resolution", "resolution"),
    "creativity": ("creativity",),
    "prompt": ("prompt", "instruction"),
    "negative_prompt": ("negative_prompt",),
    "strength": ("strength",),
    "seed": ("seed",),
    "target_fps": ("target_fps",),
    "frames_between": ("num_frames",),
    "slowdown_factor": ("slowdown_factor",),
}
COMBO_WIDGETS = ("variant", "target_resolution")

# task -> (load time, {endpoint_id: metadata})
_models = {}
# endpoint_id -> (load time, input schema)
_schemas = {}
# endpoint_id -> (load time, price text)
_prices = {}


def _get(params):
    res = requests.get(f"{API_URL}/models", params=params, timeout=15)
    res.raise_for_status()
    return res.json()


def _load_models(task):
    loaded, models = _models.get(task, (0, None))
    if models is not None and time.time() - loaded < MODELS_TTL:
        return models
    search = TASKS[task]
    found = {}
    try:
        for q in search["q"]:
            cursor = None
            while True:
                data = _get({"q": q, "category": search["category"], "status": "active", "limit": 50, **({"cursor": cursor} if cursor else {})})
                for m in data["models"]:
                    if search["keep"](m["endpoint_id"], m["metadata"]):
                        found[m["endpoint_id"]] = m["metadata"]
                cursor = data.get("next_cursor")
                if not data.get("has_more"):
                    break
    except requests.RequestException:
        # Keep using the old list while fal is unreachable or rate limited.
        if models is not None:
            return models
        raise
    _models[task] = (time.time(), found)
    return found


def models(task):
    return sorted(_load_models(task))


def _schema(endpoint_id):
    loaded, schema = _schemas.get(endpoint_id, (0, None))
    if schema is not None and time.time() - loaded < MODELS_TTL:
        return schema
    openapi = _get({"endpoint_id": endpoint_id, "expand": "openapi-3.0"})["models"][0]["openapi"]
    ref = next(ops["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"] for ops in openapi["paths"].values() if "requestBody" in ops.get("post", {}))
    components = openapi["components"]["schemas"]
    schema = components[ref.split("/")[-1]]
    # Enums are often separate components, inline them.
    for prop in schema.get("properties", {}).values():
        for option in [prop, *prop.get("anyOf", []), *prop.get("allOf", [])]:
            if "$ref" in option:
                option.update(components[option["$ref"].split("/")[-1]])
    _schemas[endpoint_id] = (time.time(), schema)
    return schema


def inputs(endpoint_id):
    """All input names of the model and the required ones."""
    schema = _schema(endpoint_id)
    return set(schema.get("properties", {})), set(schema.get("required", []))


def params(endpoint_id):
    """Node widgets the model uses: {widget: {name, type, enum, min, max, default, required}}."""
    schema = _schema(endpoint_id)
    props = schema.get("properties", {})
    found = {}
    for widget, names in PARAMS.items():
        name = next((n for n in names if n in props), None)
        if name is None:
            continue
        prop = props[name]
        option = next((o for o in [prop, *prop.get("anyOf", []), *prop.get("allOf", [])] if o.get("type") not in (None, "null")), prop)
        enum = option.get("enum")
        low, high = option.get("minimum"), option.get("maximum")
        if widget not in COMBO_WIDGETS and enum and all(isinstance(v, (int, float)) for v in enum):
            # Numbers given as a list of allowed values, e.g. creativity [0, 1].
            low, high, enum = min(enum), max(enum), None
        if (widget in COMBO_WIDGETS) != (enum is not None):
            continue
        found[widget] = {
            "name": name,
            "type": option.get("type"),
            "enum": [str(v) for v in enum] if enum else None,
            "min": low,
            "max": high,
            "default": prop.get("default", option.get("default")),
            "required": name in schema.get("required", []),
        }
    return found


def price(endpoint_id):
    """Unit price as text, empty without a loaded fal key."""
    key = keys.first("fal")
    if key is None:
        return ""
    loaded, text = _prices.get(endpoint_id, (0, None))
    if text is not None and time.time() - loaded < MODELS_TTL:
        return text
    res = requests.get(f"{API_URL}/models/pricing", params={"endpoint_id": endpoint_id}, headers={"Authorization": f"Key {key}"}, timeout=15)
    res.raise_for_status()
    prices = res.json()["prices"]
    text = " · ".join(f"{'$' if p['currency'] == 'USD' else p['currency'] + ' '}{p['unit_price']:g}/{p['unit']}" for p in prices)
    _prices[endpoint_id] = (time.time(), text)
    return text


def upload(alias, data, content_type, file_name):
    """Uploads to the fal CDN like the official fal_client and returns the URL."""
    res = requests.post(f"{REST_URL}/storage/auth/token", params={"storage_type": "fal-cdn-v3"}, headers={"Authorization": f"Key {keys.get(alias, 'fal')}"}, json={}, timeout=30)
    if not res.ok:
        raise RuntimeError(f"fal upload token · Status {res.status_code}: {res.text[:500]}")
    token = res.json()
    res = requests.post(
        f"{CDN_URL}/files/upload",
        headers={"Authorization": f"{token['token_type']} {token['token']}", "Content-Type": content_type, "X-Fal-File-Name": file_name, "X-Fal-Object-Lifecycle": LIFECYCLE},
        data=data,
        timeout=600,
    )
    if not res.ok:
        raise RuntimeError(f"fal upload · Status {res.status_code}: {res.text[:500]}")
    return res.json()["access_url"]


def run(alias, endpoint_id, payload):
    """Runs a model through the fal queue and returns its result."""
    headers = {"Authorization": f"Key {keys.get(alias, 'fal')}"}
    res = requests.post(f"{QUEUE_URL}/{endpoint_id}", headers={**headers, "X-Fal-Object-Lifecycle-Preference": LIFECYCLE}, json=payload, timeout=120)
    if not res.ok:
        raise RuntimeError(f"fal {endpoint_id} · Status {res.status_code}: {res.text[:500]}")
    job = res.json()
    start = time.time()
    status = "IN_QUEUE"
    while status in ("IN_QUEUE", "IN_PROGRESS"):
        if time.time() - start > JOB_TIMEOUT:
            raise RuntimeError(f"fal job {job['request_id']} not finished after {JOB_TIMEOUT // 60} min. Stopped waiting, the job may still run and be billed at fal.")
        time.sleep(3)
        try:
            comfy.model_management.throw_exception_if_processing_interrupted()
        except comfy.model_management.InterruptProcessingException:
            requests.put(job["cancel_url"], headers=headers, timeout=30)
            raise
        try:
            res = requests.get(job["status_url"], headers=headers, timeout=60)
        except (requests.ConnectionError, requests.Timeout):
            continue
        if res.status_code < 500:
            if not res.ok:
                raise RuntimeError(f"fal job {job['request_id']} · Status {res.status_code}: {res.text[:500]}")
            status = res.json()["status"]
    res = requests.get(job["response_url"], headers=headers, timeout=120)
    if not res.ok:
        raise RuntimeError(f"fal job {job['request_id']} · Status {res.status_code}: {res.text[:500]}")
    return res.json()


def download(url):
    res = requests.get(url, timeout=600)
    res.raise_for_status()
    return res.content


routes = PromptServer.instance.routes


@routes.get("/maybaum/fal/models/{task}")
async def list_models(request):
    task = request.match_info["task"]
    if task not in TASKS:
        raise web.HTTPNotFound()
    try:
        return web.json_response(await asyncio.to_thread(models, task))
    except requests.RequestException as e:
        return web.json_response({"error": f"Could not load models from fal: {e}"}, status=502)


@routes.get("/maybaum/fal/params")
async def get_params(request):
    try:
        return web.json_response(await asyncio.to_thread(params, request.query["model"]))
    except requests.RequestException as e:
        return web.json_response({"error": f"Could not load parameters from fal: {e}"}, status=502)


@routes.get("/maybaum/fal/price")
async def get_price(request):
    try:
        text = await asyncio.to_thread(price, request.query["model"])
    except requests.RequestException:
        text = ""
    return web.json_response({"text": text})
