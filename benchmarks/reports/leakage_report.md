# Leakage report

**STATUS: PASS**

- sequences: 57
- splits: ['excluded', 'test', 'train', 'validation']

## checks performed
1. every sequence in exactly one split
1b. author sub-segments of one drive (S3a/b/c, Vta01a/b, ...) stay in the same split
2. no GNSS / reference field in the model input feature list
3. window channel count matches the declared feature list
4. windows never cross a sequence boundary or a logging gap (enforced in windowing.py)
5. input window ends at t; target taken at t (+horizon) - no past-of-target rows in X

No issues found.
