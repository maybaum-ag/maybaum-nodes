from typing_extensions import override

from comfy_api.latest import ComfyExtension, io

from .nodes_fal import MaybaumFalImageUpscale, MaybaumFalVideoInterpolate, MaybaumFalVideoUpscale
from .nodes_keys import MaybaumAPIKey
from .nodes_openrouter import MaybaumOpenRouterImage, MaybaumOpenRouterVideo

WEB_DIRECTORY = "./web"


class MaybaumExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [MaybaumAPIKey, MaybaumOpenRouterImage, MaybaumOpenRouterVideo, MaybaumFalImageUpscale, MaybaumFalVideoUpscale, MaybaumFalVideoInterpolate]


async def comfy_entrypoint() -> MaybaumExtension:
    return MaybaumExtension()
