"""Merge one record from several source systems using field ownership.

Each field has one owning (authoritative) system. The owner's value is used.
Any other system that disagrees is reported, never silently overwritten,
and a field with no owner value is reported as a blocker.
"""


def reconcile(sources, authority):
    """sources: {system: {field: value}}, authority: {field: owning system}.

    Returns (merged_record, findings). Each finding is (field, severity, detail).
    """
    merged, findings = {}, []
    fields = set()
    for record in sources.values():
        fields.update(record)

    for field in sorted(fields):
        values = {system: rec[field] for system, rec in sources.items() if field in rec}
        owner = authority.get(field)

        if owner is None:
            findings.append((field, "BLOCKER", f"no owning system defined; values={values}"))
            continue
        if owner not in values:
            findings.append((field, "BLOCKER", f"owner '{owner}' has no value; others={values}"))
            continue

        merged[field] = values[owner]
        others = {s: v for s, v in values.items() if v != values[owner]}
        if others:
            findings.append((field, "WARNING", f"{owner}={values[owner]!r} but {others}"))

    return merged, findings
