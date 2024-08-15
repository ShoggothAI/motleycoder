from dataclasses import dataclass


@dataclass
class Tag:
    rel_fname: str
    line: int
    end_line: int
    name: str
    kind: str
    docstring: str
    fname: str
    text: str
    byte_range: tuple[int, int]
    parent_names: tuple[str, ...] = ()
    language: str | None = None
    n_defs: int = 0

    @property
    def full_name(self):
        if self.kind == "ref":
            return self.name
        else:
            return tuple(list(self.parent_names) + [self.name])

    def to_tuple(self):
        return (
            self.rel_fname,
            self.line,
            self.name,
            self.kind,
            self.docstring,
            self.fname,
            self.text,
            self.byte_range,
            self.parent_names,
        )

    def __getitem__(self, item):
        return self.to_tuple()[item]

    def __len__(self):
        return len(self.to_tuple())

    def __hash__(self):
        return hash(self.to_tuple())
