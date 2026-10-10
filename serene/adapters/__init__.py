"""Infrastructure adapters implementing `serene.ports`.

Adapters may depend on the kernel; the kernel never depends on adapters.
Optional third-party SDKs (psycopg, neatlogs, Hermes) are imported only inside
their own adapter modules, never from this package root.
"""
