# Numerical computation

Read for NumPy/SciPy array work, linear algebra, sparse data, or numerical stability.

## Correctness

- Integer overflow and unintended integer arithmetic (fixed-width sums across partitions: accumulate in Python ints or int64 deliberately).
- Precision reduction without measuring the error it introduces downstream.
- Mutating a view that shares memory with another array.
- Ignoring NaN, infinity or out-of-domain values.
- Algebraically equal expressions with different stability: `expit` instead of `1 / (1 + exp(-x))`, `log1p`, `logsumexp`.
- Explicit inverses: for least squares use `numpy.linalg.lstsq` or a solver, never `inv(X.T @ X)`; inspect rank and conditioning.

## Vectorized is not cheap

```python
differences = points[:, None, :] - points[None, :, :]
```

For `points.shape == (n, p)` this allocates an `(n, n, p)` result. Broadcasting avoids copying inputs but not allocating the output. Count the output shape before running (`python-harness-data size-check dense --rows N*N --cols P`).

Temporaries: `(values - mean) / scale` allocates intermediates. For an owned, disposable float array, in-place `values -= mean; values /= scale` saves allocations; do not do it when another view or caller depends on the original.

## Resource behavior

| work                           | usual limit                      |
| ------------------------------ | -------------------------------- |
| elementwise arithmetic         | memory bandwidth, temporaries    |
| dense matrix multiply          | compute, layout, BLAS threads    |
| many tiny operations           | dispatch and allocation overhead |
| sparse operations              | nonzero count, index traversal   |
| large expression intermediates | peak resident memory             |

More threads do not speed up memory-bound work; matrix multiplication benefits because it does much more compute per byte.

## Sparse stays sparse

CSR storage is about `nnz * (value_bytes + index_bytes) + (rows + 1) * pointer_bytes`. Densifying stores `rows * cols`: a million documents by 100,000 terms is 100 billion entries regardless of how few terms each document uses. Watch for implicit densification (`.toarray()`, `np.asarray`, some scalers without `with_mean=False`).

## Acceleration, when measured

Numba for a supported numerical loop that profiling shows is hot. CuPy when enough work stays on the GPU to pay for transfers and allocation; moving small operations back and forth is slower than staying on the CPU.

## Docs

[broadcasting](https://numpy.org/doc/stable/user/basics.broadcasting.html), [lstsq](https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html), [SciPy](https://docs.scipy.org/doc/scipy/tutorial/index.html), [Numba](https://numba.readthedocs.io/en/stable/user/5minguide.html), [CuPy](https://docs.cupy.dev/en/stable/overview.html)
