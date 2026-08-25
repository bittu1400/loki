"""Abstract provider and normalised outcome types.

Five outcomes as distinct types — a correctness requirement (pitfall C1):
success, rate-limited, transient failure, permanent failure, model
unavailable. Only the first three are fallback-eligible.
"""
