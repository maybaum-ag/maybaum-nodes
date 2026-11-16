from comfy_api.latest import io

from . import keys

Client = io.Custom("MAYBAUM_CLIENT")


class MaybaumAPIKey(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MaybaumAPIKey",
            display_name="API Key",
            category="Maybaum",
            description="Selects a client. One alias holds an OpenRouter key, a fal key or both. Keys live only in RAM and are lost on restart.",
            inputs=[
                io.Combo.Input("alias", options=[], tooltip="Client alias. Add keys via «Manage keys»."),
            ],
            outputs=[Client.Output(display_name="client")],
        )

    @classmethod
    def validate_inputs(cls, alias):
        return keys.check_alias(alias)

    @classmethod
    def execute(cls, alias):
        return io.NodeOutput(alias)
