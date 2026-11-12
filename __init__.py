from typing_extensions import override

from comfy_api.latest import ComfyExtension, io

from .nodes_openrouter import MaybaumOpenRouterImage, MaybaumOpenRouterKunde, MaybaumOpenRouterVideo

WEB_DIRECTORY = "./web"


class MaybaumExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [MaybaumOpenRouterKunde, MaybaumOpenRouterImage, MaybaumOpenRouterVideo]


async def comfy_entrypoint() -> MaybaumExtension:
    return MaybaumExtension()
