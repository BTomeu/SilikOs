# silik eda try device: a silicon pn diode in one dimension, simulated by DEVSIM (drift-diffusion with
# Shockley-Read-Hall recombination; DEVSIM's own silicon parameters at 300 K). The p side is at the contact "top",
# so a positive bias there is forward. The exercise's doping (1e18 cm-3 on each side of an abrupt junction, 0.1 um
# long) is not a real device's. What is checked is physics: it conducts forward, blocks in reverse, and its forward
# current grows with the bias.
import devsim
from devsim.python_packages import model_create, simple_physics

dev, reg = "diode", "bulk"
devsim.create_1d_mesh(mesh="m")
devsim.add_1d_mesh_line(mesh="m", pos=0, ps=1e-7, tag="top")
devsim.add_1d_mesh_line(mesh="m", pos=0.5e-5, ps=1e-9, tag="mid")
devsim.add_1d_mesh_line(mesh="m", pos=1e-5, ps=1e-7, tag="bot")
devsim.add_1d_contact(mesh="m", name="top", tag="top", material="metal")
devsim.add_1d_contact(mesh="m", name="bot", tag="bot", material="metal")
devsim.add_1d_region(mesh="m", material="Si", region=reg, tag1="top", tag2="bot")
devsim.finalize_mesh(mesh="m")
devsim.create_device(mesh="m", device=dev)

simple_physics.SetSiliconParameters(dev, reg, 300)
devsim.set_parameter(device=dev, region=reg, name="taun", value=1e-8)
devsim.set_parameter(device=dev, region=reg, name="taup", value=1e-8)
model_create.CreateNodeModel(dev, reg, "Acceptors", "1.0e18*step(0.5e-5-x)")
model_create.CreateNodeModel(dev, reg, "Donors", "1.0e18*step(x-0.5e-5)")
model_create.CreateNodeModel(dev, reg, "NetDoping", "Donors-Acceptors")

# the potential alone first, then electrons and holes with it
model_create.CreateSolution(dev, reg, "Potential")
simple_physics.CreateSiliconPotentialOnly(dev, reg)
for c in devsim.get_contact_list(device=dev):
    devsim.set_parameter(device=dev, name=simple_physics.GetContactBiasName(c), value=0.0)
    simple_physics.CreateSiliconPotentialOnlyContact(dev, reg, c)
devsim.solve(type="dc", absolute_error=1.0, relative_error=1e-10, maximum_iterations=30)
model_create.CreateSolution(dev, reg, "Electrons")
model_create.CreateSolution(dev, reg, "Holes")
devsim.set_node_values(device=dev, region=reg, name="Electrons", init_from="IntrinsicElectrons")
devsim.set_node_values(device=dev, region=reg, name="Holes", init_from="IntrinsicHoles")
simple_physics.CreateSiliconDriftDiffusion(dev, reg)
for c in devsim.get_contact_list(device=dev):
    simple_physics.CreateSiliconDriftDiffusionAtContact(dev, reg, c)
devsim.solve(type="dc", absolute_error=1e10, relative_error=1e-10, maximum_iterations=30)


def current(volts):
    """the current density at the contact "top" (A/cm2) with that bias on it"""
    devsim.set_parameter(device=dev, name=simple_physics.GetContactBiasName("top"), value=volts)
    devsim.solve(type="dc", absolute_error=1e10, relative_error=1e-10, maximum_iterations=30)
    return sum(devsim.get_contact_current(device=dev, contact="top", equation=e)
               for e in ("ElectronContinuityEquation", "HoleContinuityEquation"))


steps = [0.1, 0.2, 0.3, 0.4, 0.5]
found = {}
for v in steps:                                   # up to 0.5 V forward
    found[v] = current(v)
for v in reversed(steps[:-1]):                    # back down
    current(v)
found[0.0] = current(0.0)
for v in steps:                                   # down to 0.5 V reverse
    found[-v] = current(-v)

print("")
for v in sorted(found):
    print("IV %+.1f V %+.4e A/cm2" % (v, found[v]))
forward, reverse = abs(found[0.5]), abs(found[-0.5])
grows = all(abs(found[b]) > abs(found[a]) for a, b in zip(steps, steps[1:]))
print("%s rectifies: forward %.3e A/cm2 at 0.5 V, reverse %.3e A/cm2 at -0.5 V" % ("PASS" if forward > 1000 * reverse else "FAIL", forward, reverse))
print("%s grows: the forward current rises with each 0.1 V" % ("PASS" if grows else "FAIL"))
# ("custom" is DEVSIM's name for a solver given to it from Python: the UMFPACK that comes with it, said at the top)
print("solver %s; BLAS and LAPACK from %s" % (devsim.get_parameter(name="direct_solver"), (devsim.get_parameter(name="info").get("math_libraries") or ["?"])[0]))
