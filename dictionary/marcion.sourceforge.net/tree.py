import itertools
import typing

import constants
import pandas as pd
import parse

NUM_COLS = 10
assert not 100 % NUM_COLS


class node:
    def __init__(self, row: pd.Series) -> None:
        self._row = row
        self._descendants: list[node] = []

        # Descendant information.
        self._preprocessed = False
        self._key_to_idx: dict[str, int] = {}

    def row(self) -> pd.Series:
        return self._row

    def is_root(self) -> bool:
        return "key_word" not in self._row

    def cell(self, key: str) -> str:
        return str(self.row()[key])

    def add_descendant(self, descendant) -> None:
        assert self.is_root()
        assert isinstance(descendant, node)
        assert descendant.cell("key_word") == self.cell("key")
        assert not self._preprocessed
        self._descendants.append(descendant)

    def preprocess(self) -> None:
        assert self.is_root()
        assert not self._preprocessed
        # Sort.
        self._descendants = sorted(
            self._descendants,
            key=lambda n: int(n.cell("pos")),
        )
        # Populate the field needed for retrieving children by key.
        self._key_to_idx = {
            d.cell("key"): idx for idx, d in enumerate(self._descendants)
        }
        self._preprocessed = True

    def dialects(self) -> list[str]:
        dialects = {
            dialect.strip()
            for child in self.descendants(include_root=True)
            for dialect in child.cell("dialects").split(",")
            if dialect
        }
        assert all(d in constants.DIALECTS for d in dialects)
        return sorted(dialects)

    def child(self, key: str):
        assert self.is_root()
        assert self._preprocessed
        return self._descendants[self._key_to_idx[key]]

    def descendants(self, include_root: bool = False):
        assert self.is_root()
        assert self._preprocessed
        return (
            [self] + self._descendants if include_root else self._descendants
        )

    def crum_page_range(self) -> str:
        assert self.is_root()
        assert self._preprocessed
        pages: list[parse.crum_page] = [
            parse.parse_crum_cell(d.row()["crum"])
            for d in self.descendants(include_root=True)
        ]
        pages = [p for p in pages if p.real()]
        if not pages:
            return ""
        if len(pages) == 1:
            return pages[0].string()
        ordered: list[parse.crum_page] = list(sorted(pages))
        first, last = ordered[0], ordered[-1]
        if first == last:
            assert all(p == first for p in ordered)
            return first.string()
        return f"{first.string()}-{last.string()}"

    def parent(self, child, include_root: bool = False):
        assert not include_root, "Not yet implemented!"
        assert self._preprocessed
        assert self.is_root()
        assert not child.is_root()
        assert isinstance(child, node)
        p = child.cell("key_deriv")
        if not int(p):
            return None
        return self._descendants[self._key_to_idx[p]]

    def index(self, child) -> int:
        assert isinstance(child, node)
        assert self.is_root()
        assert self._preprocessed
        return self._key_to_idx[child.cell("key")]

    def html_table(
        self,
        explain: bool = True,
        include_root: bool = False,
    ) -> str:
        """
        We use the following fields from each child:
        - depth
        - word-parsed-classify
        - type-parsed
        - en-parsed
        - crum
        - key
        They are expected to be pre-sorted, and to belong to a single word.
        The per-dialected columns are used, but not included in the output.

        Args:
            explain: If true, include the meaning, type, and Crum page number.
        """
        return "".join(self.html_table_aux(explain, include_root))

    def html_table_aux(
        self,
        explain: bool = True,
        include_root: bool = False,
    ) -> typing.Generator[str]:
        assert (
            not include_root
        ), "An HTML tree with the root is not yet supported."
        assert self.is_root()
        assert self._preprocessed

        descendants = self.descendants()
        if not descendants:
            return
        crum_row_spans = build_crum_row_spans(descendants)

        yield '<table class="derivations" id="derivations">'
        yield "<colgroup>"
        for _ in range(NUM_COLS):
            yield f'<col style="width: {100/NUM_COLS}%;">'
        yield "</colgroup>"

        for d, crum_row_span in zip(descendants, crum_row_spans):
            crum, crum_span = crum_row_span
            if not crum_span:
                assert not crum
            if not crum:
                crum_span = 0
            if not explain:
                crum, crum_span = "", 0
            depth = int(d.cell("depth"))
            word = d.cell("word-parsed-classify")
            type = d.cell("type-parsed")
            meaning = d.cell("en-parsed")
            key = d.cell("key")
            word_width = int((NUM_COLS - depth) / 2) if word else 0
            # We keep the meaning column regardless of whether a meaning is
            # actually present. However, if the whole table is to be generated
            # without a meaning, we remove it.
            meaning_width = NUM_COLS - word_width - depth - 1
            if not explain and type != "HEADER":
                # Skip the English.
                meaning_width = 0
            assert word_width or meaning_width
            hyperlink = (
                f'<span hidden="" class="drv-key dev right">{key}</span>'
            )
            # New row.
            yield f'<tr id="drv{key}" class="drv">'
            # Margin.
            yield f'<td colspan="{depth}"></td>' if depth else ""
            # Word.
            if word_width:
                yield f'<td colspan="{word_width}" class="marcion bordered">'
                yield word
                if not meaning_width:
                    yield hyperlink
                yield "</td>"
            # Meaning.
            if meaning_width:
                yield f'<td colspan="{meaning_width}" class="meaning bordered">'
                if type not in ["-", "HEADER"]:
                    yield f"<b>({type})</b><br/>"
                yield meaning
                yield hyperlink
                yield "</td>"
            if crum_span:
                yield f'<td rowspan="{crum_span}" class="dictionary bordered">'
                yield "<b>Crum: </b>"
                yield f'<span class="crum-page">{crum}</span>'
                yield "</td>"

            # End row.
            yield "</tr>"
        yield "</table>"

    def html_list(self, include_root: bool = False) -> str:
        return "".join(self.html_list_aux(include_root))

    def html_list_aux(
        self,
        include_root: bool = False,
    ) -> typing.Generator[str]:
        assert (
            not include_root
        ), "An HTML tree with the root is not yet supported."
        assert self.is_root()
        assert self._preprocessed

        descendants = self.descendants()
        if not descendants:
            return

        yield "<ul>"

        depth = 0
        for d in descendants:
            cur_depth = int(d.cell("depth"))
            while cur_depth > depth:
                yield "<li>"
                yield "<ul>"
                depth += 1
            while cur_depth < depth:
                yield "</ul>"
                yield "</li>"
                depth -= 1
            word = d.cell("word-parsed-prettify")
            type = d.cell("type-parsed")
            # Calling the parser in tree? A little unorthodox, eh?!
            meaning = parse.lighten_greek(d.cell("en-parsed"))
            assert word or (type == "HEADER" and meaning)
            if type and type not in ["-", "HEADER"]:
                meaning = f"({type}) {meaning}"
            yield "<li>"
            yield "<br/>".join(filter(None, [word, meaning]))
            yield "</li>"

        while depth > 0:
            yield "</ul>"
            yield "</li>"
            depth -= 1
            yield "</ul>"


def depths(derivations: pd.DataFrame) -> list[int]:
    keys = [int(row["key"]) for _, row in derivations.iterrows()]
    parents = [int(row["key_deriv"]) for _, row in derivations.iterrows()]
    key_to_parent = {k: p for k, p in zip(keys, parents)}

    def depth(key: int) -> int:
        parent = key_to_parent[key]
        if not parent:
            return 0
        return 1 + depth(parent)

    depths = [depth(k) for k in keys]
    assert all(0 <= x <= constants.MAX_DERIVATION_DEPTH for x in depths)
    return depths


def build_crum_row_spans(nodes: list[node]) -> list[tuple[str, int]]:
    crum_column = [d._row["crum"] for d in nodes]
    out = []
    for group in itertools.groupby(crum_column):
        # Validate that all elements are equal.
        crum = group[0]
        repetitions = len(list(group[1]))
        out.append((crum, repetitions))
        for _ in range(repetitions - 1):
            out.append(("", 0))
    return out


def build_has_cell(tree: node, cell_name: str) -> list[bool]:
    assert tree.is_root()
    has_cell = [False for _ in tree.descendants()]
    for idx, d in enumerate(tree.descendants()):
        if d.cell(cell_name):
            has_cell[idx] = True
            # Travel up the tree!
            while True:
                d = tree.parent(d)
                if not d:
                    break
                has_cell[tree.index(d)] = True

    return has_cell
