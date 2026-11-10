# KLayout, without a screen (klayout -zz -r gds_read.py -rd gds=FILE): reads a GDS file and says what is in it
import pya

layout = pya.Layout()
layout.read(gds)   # noqa: F821  (the variable comes from -rd gds=FILE)
cell = layout.top_cell()
shapes = sum(cell.shapes(i).size() for i in layout.layer_indexes())
print("read %s: %d shapes on %d layers, %s" % (cell.name, shapes, layout.layers(), cell.bbox()))
