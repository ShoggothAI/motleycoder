from dataclasses import dataclass, field
from typing import Set


@dataclass
class RepoMapArgs:
    chat_fnames: Set[str] = field(default_factory=set)
    other_fnames: Set[str] = field(default_factory=set)
    mentioned_fnames: Set[str] = field(default_factory=set)
    mentioned_idents: Set[str] = field(default_factory=set)
    mentioned_entities: Set[str] = field(default_factory=set)
    search_terms: Set[str] = field(default_factory=set)
    add_prefix: bool = True
