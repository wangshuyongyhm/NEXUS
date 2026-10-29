"""NEXUS meta package (skeleton).

The real components live in packages/ (nexusos-* lockstep 1.0.0):
- nexusos-common — shared anchors + `nexus` CLI (init/doctor)
- nexusos-gate   — gate engine
  name was taken by an unrelated project)
- nexusos-mem    — shared knowledge base (MEM)
- nexusos-xdr    — agent message bus (XDR)
"""

__version__ = "0.1.0"
COMPONENTS = ("nexusos-common", "nexusos-gate", "nexusos-mem", "nexusos-xdr")
