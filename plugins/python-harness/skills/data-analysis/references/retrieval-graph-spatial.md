# Retrieval, graphs, geospatial and named-dimension arrays

Read when the question is about similar records, what depends on what, physical distance or regions, or gridded scientific data. Scaling and memory for these belong to the `data-engineering` skill's `references/performance.md`.

## Text similarity and retrieval

| need                                 | pairing                                                                  |
| ------------------------------------ | ------------------------------------------------------------------------ |
| shared distinctive vocabulary        | TF-IDF + cosine similarity                                               |
| text labels                          | TF-IDF + linear classifier                                               |
| relevant text with different wording | Sentence Transformers, evaluated against TF-IDF                          |
| exploratory grouping                 | representation + clustering (KMeans fixed k; HDBSCAN with a noise label) |

```python
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

incidents = pd.DataFrame(
    {
        'id': ['INC-101', 'INC-102', 'INC-103'],
        'summary': [
            'Postgres connection pool exhausted; requests timing out',
            'TLS certificate expired; handshake failures',
            'Database pool timeout after worker concurrency increased',
        ],
    }
)
vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
documents = vectorizer.fit_transform(incidents['summary'])
query = vectorizer.transform(['postgres connection pool timeout'])
ranked = incidents.assign(similarity=cosine_similarity(query, documents).ravel()).nlargest(
    2, 'similarity'
)
```

- Cosine similarity is a ranking score, not a probability, and similar text is not the same root cause.
- Default tokenization can split error codes and paths; check that important technical tokens survive.
- Evaluate retrieval with relevance judgments (recall@k, MRR) on held-out queries; deduplicate near-identical records first or they inflate the score.
- Labels or descriptions written after the prediction time are leakage.
- Add embeddings only for demonstrated vocabulary mismatch, measured against the lexical baseline.

## Graphs: reachability and blast radius

Define what an edge means before running anything. "Service depends on dependency", "calls", "starts after", "owns" and "can assume role" are different graphs; never merge them.

```python
import networkx as nx

dependencies = nx.DiGraph(
    [
        ('web', 'api'),
        ('web', 'auth'),
        ('api', 'postgres'),
        ('api', 'redis'),
        ('worker', 'postgres'),
        ('auth', 'postgres'),
    ]
)
potentially_affected = nx.ancestors(dependencies, 'postgres')
cycles = [
    component for component in nx.strongly_connected_components(dependencies) if len(component) > 1
]
```

With edges pointing from dependent to dependency, `ancestors(postgres)` is everything that transitively depends on it: here `{web, api, worker, auth}`; set order is unspecified. If edges point the other way, use `descendants` or reverse the graph. Reachability is potential impact; fallbacks, caches, optional paths and graceful degradation decide actual impact, so say so. Multi-node strongly connected components are dependency cycles; check self-loops separately if they count. A centrality score is not importance until its definition matches the question.

## Geospatial

- Assigning a CRS (`set_crs`) labels coordinates; transforming (`to_crs`) changes them. Do not confuse the two.
- Never compute physical distance in longitude/latitude degrees; use a geodesic method or a projection suited to the region and measurement.
- Align CRSs before joins and overlays; check invalid geometries, boundaries and overlaps.
- Prefer spatial joins (they use spatial indexes) over Python loops over geometry pairs; filter to the region first; simplify geometry only when lost detail is acceptable.

## Named-dimension arrays (xarray)

Name dimensions and coordinates to avoid axis mix-ups, units mismatches and accidental expansion of the coordinate space on alignment. Missing cells are not observed zeros. Storage is the product of dimension sizes; labels do not shrink it. Chunking and `.compute()` placement are engineering concerns.

## Docs

[text feature extraction](https://scikit-learn.org/stable/modules/feature_extraction.html), [Sentence Transformers](https://www.sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html), [HDBSCAN](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html), [NetworkX ancestors](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.dag.ancestors.html), [GeoPandas projections](https://geopandas.org/en/stable/docs/user_guide/projections.html), [why xarray](https://docs.xarray.dev/en/stable/getting-started-guide/why-xarray.html)
