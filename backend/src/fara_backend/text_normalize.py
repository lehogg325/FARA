from __future__ import annotations


def norm(text: str) -> str:
    return " ".join(text.strip().lower().split())


# Same normalization as norm() above, expressed in SQL for GROUP BY — kept in exact
# lockstep (strip, lowercase, collapse internal whitespace) so grouped counts here
# match norm()'s grouping in Python. Never fuzzy — whitespace/case variance only,
# consistent with this project's "raw and unresolved, never fuzzy-merged" search
# and graph identity conventions.
NORM_SQL = "lower(regexp_replace(trim({col}), '\\s+', ' ', 'g'))"
