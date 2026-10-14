def choose_connector(connectors, required_power):
    """Return the lowest-power available compatible connector, or None."""
    required = float(required_power)
    compatible = [c for c in connectors
                  if c.get("status", "AVAILABLE") == "AVAILABLE"
                  and float(c.get("max_power_kw", 0)) >= required]
    return min(compatible, key=lambda c: float(c["max_power_kw"])) if compatible else None
