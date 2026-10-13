# Visualization

Read before making any chart for an analysis. If a dedicated charting or dataviz skill is available, follow it for palette and styling; this file covers which chart answers which comparison and what makes a chart dishonest.

| question                              | chart                                     | pairing              |
| ------------------------------------- | ----------------------------------------- | -------------------- |
| distribution of latency or cost       | histogram, ECDF, box plot                 | seaborn + Matplotlib |
| how groups differ                     | distributions or estimates with intervals | seaborn + Matplotlib |
| change over time                      | line chart                                | Matplotlib or Plotly |
| relation of two measures              | scatter                                   | seaborn or Plotly    |
| category counts                       | sorted bar chart                          | Matplotlib or Plotly |
| co-variation of many numeric features | correlation heatmap (not causal)          | seaborn              |
| exploration with hover and zoom       | interactive chart                         | Plotly               |
| linked filters, declarative encodings | linked views                              | Altair               |
| far more points than pixels           | density or pixel aggregation              | Datashader           |

Rules:

- Do not hide a long tail behind a mean; show the distribution or a high quantile with counts.
- Show uncertainty wherever the comparison depends on it.
- Label units, time window, population and what the estimate is; no color-only meaning; no truncated axes that exaggerate a difference.
- Sampling must keep the events the question is about (incident windows, extremes).
- Plot the reduced result, not the raw table: aggregate in the engine, chart the summary.
- The plotting function returns the figure; the caller saves it at the publication boundary and closes it.

A fast dataframe does not mean a fast browser chart: serialization, transfer and rendering cost scale with marks sent. Send only what the view can show.

## Docs

[seaborn](https://seaborn.pydata.org/introduction.html), [Plotly](https://plotly.com/python/), [Altair data](https://altair-viz.github.io/user_guide/data.html), [Datashader pipeline](https://datashader.org/getting_started/Pipeline.html)
