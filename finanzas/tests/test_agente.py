from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

import lib.agente as ag


class FakeMessages:
    def __init__(self):
        self.n = 0
        self.llamadas = []

    def create(self, **kw):
        self.llamadas.append(kw)
        self.n += 1
        u = Usage(input_tokens=1, output_tokens=1)
        if self.n == 1:
            return Message(id="m1", type="message", role="assistant", model="x", usage=u, stop_reason="tool_use",
                content=[TextBlock(type="text", text="Reviso."), ToolUseBlock(type="tool_use", id="t1", name="ranking_rentabilidad", input={"desde": "2026-01-01", "hasta": "2026-10-31"})])
        return Message(id="m2", type="message", role="assistant", model="x", usage=u, stop_reason="end_turn",
            content=[TextBlock(type="text", text="Pucón fue la mejor.")])

class FakeClient:
    def __init__(self): self.messages = FakeMessages()

def test_ciclo(monkeypatch):
    vistos = {}
    def fake(nombre, args, permitidas):
        vistos.update(nombre=nombre, permitidas=permitidas)
        return '[{"propiedad_id":"PUCON","resultado":1}]'
    monkeypatch.setattr(ag, "ejecutar_herramienta", fake)
    c = FakeClient()
    texto, hist = ag.responder([{"role": "user", "content": "¿mejor propiedad?"}], ["PUCON"], cliente=c)
    assert texto == "Pucón fue la mejor."
    assert vistos == {"nombre": "ranking_rentabilidad", "permitidas": ["PUCON"]}
    assert hist[2]["content"][0]["type"] == "tool_result" and len(hist) == 4
    assert c.messages.llamadas[1]["messages"][1]["content"][1]["type"] == "tool_use"
