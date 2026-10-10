"""Serene Memory Repo: Git + Markdown durable memory, and the Dream pipeline.

Experience is the Postgres ledger; memory is consolidated, reviewed knowledge
in Git + Markdown; belief is investigation / Causal Twin state rebuilt from the
ledger. Many components propose `MemoryPatch`es; only the Memory Committer
(`serene.memory.committer`) mutates memory_repo, after the deterministic
Critic (`serene.memory.critic`) passes. Dream (`serene.memory.dream`) only
proposes.

This package root deliberately imports nothing: the ledger's admission imports
`serene.memory.critic`, and the committer / Dream import the ledger.
"""
