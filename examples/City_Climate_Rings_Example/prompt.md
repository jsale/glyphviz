The prompt this scene was made from, given to Claude with the glyphviz skill
loaded, together with `city_climate.csv`. `build_climate_rings.py` is the
generator Claude wrote for it, and `climate_rings_gv_node.csv` is its output.
The "Your Data in GlyphViz" lesson video shows this prompt on screen.

---

Here's a spreadsheet of monthly climate for 31 cities: city, country,
latitude, longitude, month, average high, average low, mean temperature, and
rainfall in mm.

Make it a GlyphViz scene. Put each city on a globe. Around each city, draw a
ring of the 12 months like a clock face, January at the top, coloured by mean
temperature from blue to red. On each month, stand a bar from the average low
to the average high, and a blue column for that month's rainfall. Label
everything.
