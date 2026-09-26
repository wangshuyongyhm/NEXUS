"""NEXUS meta package (skeleton).

The real components live in packages/:
- nexus-gatekit  — gate engine (renamed from private 'nexus-gate'; the PyPI
  name was taken by an unrelated project)
- nexus-mem      — shared knowledge base (MEM)
- nexus-xdr      — agent message bus (XDR)
"""

__version__ = "0.1.0"
COMPONENTS = ("nexus-gatekit", "nexus-mem", "nexus-xdr")
