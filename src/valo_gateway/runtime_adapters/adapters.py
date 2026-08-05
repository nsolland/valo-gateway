from valo_gateway.harness import BaseRuntimeAdapter
class LocalRuntime(BaseRuntimeAdapter): backend = "local"
class OpenAIRuntime(BaseRuntimeAdapter): backend = "openai"
class ClaudeRuntime(BaseRuntimeAdapter): backend = "claude"
class GoogleRuntime(BaseRuntimeAdapter): backend = "google"
