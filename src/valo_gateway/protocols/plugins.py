from .base import MappingIngress
class MCPIngress(MappingIngress): protocol = "mcp"
class A2AIngress(MappingIngress): protocol = "a2a"
class HTTPIngress(MappingIngress): protocol = "http"
class GRPCIngress(MappingIngress): protocol = "grpc"
class ExtAuthzIngress(MappingIngress): protocol = "ext_authz"
