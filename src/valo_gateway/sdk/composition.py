from dataclasses import dataclass

from valo_gateway.gateway import RuntimeControlPlane, ValoGateway
from valo_gateway.harness import HarnessRouter
from valo_gateway.protocols import IngressNormalizer
from valo_gateway.tool_adapters import ToolRegistry


@dataclass
class GatewaySDK:
    ingress: IngressNormalizer
    harness: HarnessRouter
    tools: ToolRegistry
    gateway: ValoGateway
    @classmethod
    def compose(cls, *, ingress: IngressNormalizer, harness: HarnessRouter,
                tools: ToolRegistry, control_plane: RuntimeControlPlane | None = None) -> "GatewaySDK":
        return cls(ingress, harness, tools, ValoGateway(control_plane))
