import asyncio

import requests
from aiohttp import web
from server import PromptServer

PROVIDERS = {"openrouter": "OpenRouter", "fal": "fal"}
# provider -> (URL, auth scheme). A GET with a valid key returns 200.
VERIFY = {
    "openrouter": ("https://openrouter.ai/api/v1/key", "Bearer"),
    "fal": ("https://api.fal.ai/v1/models/pricing?endpoint_id=fal-ai/flux/dev", "Key"),
}

# Keys live only in this process's RAM. Never store, log or return them.
# alias -> {provider: key}
_keys = {}


def check_alias(alias):
    if alias in _keys:
        return True
    return f"No keys loaded for alias '{alias}'. Add them on the «API Key» node via «Manage keys»."


def get(alias, provider):
    key = _keys.get(alias, {}).get(provider)
    if key is None:
        raise ValueError(f"No {PROVIDERS[provider]} key loaded for alias '{alias}'. Add it on the «API Key» node via «Manage keys».")
    return key


def first(provider):
    """Any loaded key of a provider. Only for lookups that bill nobody, like prices."""
    return next((k[provider] for k in _keys.values() if provider in k), None)


def _verify(provider, key):
    url, scheme = VERIFY[provider]
    return requests.get(url, headers={"Authorization": f"{scheme} {key}"}, timeout=15)


def _listing():
    return {alias: [PROVIDERS[p] for p in sorted(keys)] for alias, keys in sorted(_keys.items())}


routes = PromptServer.instance.routes


@routes.get("/maybaum/keys/aliases")
async def list_aliases(request):
    return web.json_response(sorted(_keys))


@routes.get("/maybaum/keys")
async def list_keys(request):
    return web.json_response(_listing())


@routes.post("/maybaum/keys")
async def add_keys(request):
    data = await request.json()
    alias = str(data.get("alias", "")).strip()
    new = {p: str(data.get(p) or "").strip() for p in PROVIDERS}
    new = {p: k for p, k in new.items() if k}
    if not alias or not new:
        return web.json_response({"error": "Enter an alias and at least one key."}, status=400)
    result = {"alias": alias}
    for provider, key in new.items():
        res = await asyncio.to_thread(_verify, provider, key)
        if not res.ok:
            return web.json_response({"error": f"{PROVIDERS[provider]} rejected the key (status {res.status_code}). Nothing saved."}, status=400)
        if provider == "openrouter":
            info = res.json().get("data", {})
            result.update(label=info.get("label"), limit_remaining=info.get("limit_remaining"), usage=info.get("usage"))
    _keys.setdefault(alias, {}).update(new)
    result["providers"] = [PROVIDERS[p] for p in sorted(_keys[alias])]
    return web.json_response(result)


@routes.delete("/maybaum/keys/{alias}")
async def delete_keys(request):
    _keys.pop(request.match_info["alias"], None)
    return web.json_response(_listing())
