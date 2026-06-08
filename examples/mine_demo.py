"""faultline mode-5 (invariant MINING): the tool learns the rules itself, then catches a regression.

No human writes the test. faultline watches a few good runs of an order/shipping agent, learns the
rules (validate before ship, both always called), then a refactor ships WITHOUT validating - and a
rule nobody wrote fires.
"""
import faultline as fl
from faultline.mine import mine

VALID = {"123 Main St", "55 Oak Ave"}

@fl.tool
def validate_address(addr):
    return addr in VALID

@fl.tool
def ship_package(addr):
    return "shipped to " + addr

def good_agent(addr):                       # the trusted behavior
    ok = validate_address(addr)
    if ok:
        ship_package(addr)
    return {"status": "shipped" if ok else "rejected"}

def regressed_agent(addr):                  # after a refactor: ships WITHOUT validating
    ship_package(addr)
    return {"status": "shipped"}

if __name__ == "__main__":
    spec = mine(good_agent, ["123 Main St", "55 Oak Ave"])     # the tool watches good runs
    spec.report()
    print("\n--- enforce the self-learned spec on the new (regressed) agent ---")
    run = fl.run_once(regressed_agent, "123 Main St")
    hits = spec.check(run)
    for v in hits:
        print("  ⚠ CAUGHT:", v)
    if not hits:
        print("  (no violation)")
