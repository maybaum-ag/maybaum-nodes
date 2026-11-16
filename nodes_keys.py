from comfy_api.latest import io

from . import keys

APIKey = io.Custom("MAYBAUM_API_KEY")


class MaybaumAPIKey(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MaybaumAPIKey",
            display_name="API Key",
            category="Maybaum",
            description="Selects a key alias for the other Maybaum nodes. An alias holds an OpenRouter key, a fal key or both. Keys live only in memory and are lost on restart.",
            inputs=[
                io.Combo.Input("alias", options=[], tooltip="Key alias. Add keys via «Manage keys»."),
            ],
            outputs=[APIKey.Output(display_name="API Key")],
        )

    @classmethod
    def validate_inputs(cls, alias):
        return keys.check_alias(alias)

    @classmethod
    def execute(cls, alias):
        return io.NodeOutput(alias)
