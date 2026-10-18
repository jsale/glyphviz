# Vehicle Sales — Depreciation Grid

A make × model-year bar field: bar height is median selling price, so every make's depreciation curve stands in relief; bar radius is sales volume.

![Vehicle Sales — Depreciation Grid loaded in GlyphViz](../assets/examples/vehicle-depreciation-grid.png)

*Data: Kaggle used-vehicle auction dataset (~559,000 sale records).*

**Try it:** download this example below (or [the full examples set](../getting-started/installation.md#example-scenes)), then open `Vehicle_Sales_Example/Depreciation_Grid/DepreciationGrid_gv_node.csv` — or just drag its folder onto the GlyphViz window.

[:material-download: Download this example (13 KB)](https://iluvdata.org/glyphviz/zips/Vehicle_Sales_Example_Depreciation_Grid.zip){ .md-button }

## What it is

How fast does a car lose its value? The answer for a half-million real auction sales is a field of bars. Each bar is one make in one model year: **20 makes by 18 model years, 338 bars in all**, standing on a wire grid. Look along any row and the tops of the bars trace that make's **depreciation curve in relief**, rising from the old cars on the left to the new ones on the right.

The data are Kaggle's used-vehicle auction records, about 559,000 sales. A half-million messy records have been boiled down to a few hundred glyphs, and every attribute of every glyph is a statistic, so market structure you were not looking for is just visible.

## How to read it

| Axis or property | Meaning |
|---|---|
| **X (columns)** | model year, from 1998 on the left to 2015 on the right |
| **Y (rows)** | make, ordered **cheap to luxury, away from the viewer**: Volkswagen and Mazda at the front, then Chrysler, Dodge, Chevrolet and on, to Lexus and Mercedes-Benz at the back |
| **Bar height** | **median selling price**: the depreciation curve for that make |
| **Bar radius** | sales volume, on a square-root scale, so a fat bar is a car that sold in numbers |
| **Bar colour** | median odometer reading, from dark blue for low mileage to yellow for high |

Click a bar for its numbers, for example *Volkswagen 1999 | 74 sold | median $1.0k | -6.4% vs MMR | 127k mi*. MMR is the Manheim Market Report, the wholesale book value the sale is compared with. A make's whole row is labelled with its median price, for example *Volkswagen (median $9.8k)*.

## What to look for

- **The curves slope up to the right.** Along each row the bars climb as the model years get newer. That is depreciation, drawn: a car is worth less each year older it gets.
- **Luxury rows stand taller.** The tallest bars in the back rows (Mercedes-Benz, Lexus, Infiniti, BMW and Audi) reach roughly two to four times the height of the tallest bars at the front, which is the point of ordering the rows by price.
- **Colour follows age.** The oldest bars are yellow, because old cars have high mileage, and the newest are dark blue. The colour is a second view of the same axis, so a bar whose colour does not match its neighbours' is a make-and-year with unusual mileage.
- **Radius is where the volume is.** Look for the years and makes with the fattest bars: they make up most of the sales.

## Things to try

- **Compare two makes** by orbiting to look straight along the X axis, so that two rows overlay.
- **Read the oldest cars.** The leftmost bars are the cheapest and the highest mileage; the tags give the exact median prices.
- **See the same data as a galaxy.** [Market Galaxy](vehicle-market-galaxy.md) aggregates the same sales by make and model, and [Raw Auction Field](vehicle-raw-auction-field.md) shows the sales unaggregated.

## How it is built

The scene is **378 nodes**: a ground grid, a title, the 338 bars, and 38 marker spheres that label the 20 makes and 18 model years along the edges. It is a static scene with no animation, built by `generate_vehicle_sales_example.py` from the Kaggle CSV with the three Vehicle Sales scenes sharing one generator. Bars are cylinders, so the radius reads as a width rather than a flat disc.

**Data:** Kaggle used-vehicle auction dataset (about 559,000 sale records).
