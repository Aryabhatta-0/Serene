"""Serene Memory Repo: Git + Markdown durable memory, and the Dream pipeline.

Experience is the Postgres ledger; memory is consolidated, reviewed knowledge
in Git + Markdown; belief is investigation / Causal Twin state rebuilt from the
ledger. Many components propose `MemoryPatch`es; only the Memory Committer
(`serene.memory.committer`) mutates memory_repo, after the deterministic
Critic passes. Dream (`serene.memory.dream`) only proposes.

The Critic, path rules and document / diff grammar are deterministic authority
and live in the policy layer (`serene.policies.memory_review`,
`serene.policies.memory_format`); `critic`, `rules`, `document` and `diff` here
re-export them. Policy code never imports from this package.
"""
