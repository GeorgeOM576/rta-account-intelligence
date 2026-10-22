"""Widget adapters for one authoritative, workspace-scoped selection mapping."""

def set_checked(state, key, identity, item, checked):
    selected = dict(state.get(key, {}))
    if checked:
        selected.setdefault(identity, item)
    else:
        selected.pop(identity, None)
    state[key] = selected


def checkbox_changed(state, key, identity, item, widget):
    set_checked(state, key, identity, item, bool(state.get(widget, False)))


def consume_editor(state, selection_key, view_key, editor_key=None, complete=False):
    """Consume new checkbox deltas before replacing an immutable editor view.

    Ignore callbacks from retired widgets and already consumed cumulative patches.
    Text/action edits must never replay an older checkbox over a newer selection.
    """
    view = state.get(view_key)
    if not view or (editor_key is not None and view['key'] != editor_key):
        return
    seen = view.setdefault('selection_edits', {})
    changes = state.get(view['key'], {}).get('edited_rows', {})
    if complete:
        # Browser patches are cumulative: returning to the baseline removes a delta.
        active = {str(p) for p, edits in changes.items() if isinstance(edits, dict) and isinstance(edits.get('Select'), bool)}
        for index in list(seen):
            if str(index) not in active:
                checked = bool(view['data'][index]['Select'])
                set_checked(state, selection_key, view['identities'][index], view['rows'][index], checked)
                seen.pop(index)
    for position, edits in changes.items():
        try:
            index = int(position)
        except (TypeError, ValueError):
            continue
        if isinstance(position, bool) or not 0 <= index < len(view['rows']) or not isinstance(edits, dict):
            continue
        checked = edits.get('Select')
        if not isinstance(checked, bool) or seen.get(index) == checked:
            continue
        identity, item = view['identities'][index], view['rows'][index]
        set_checked(state, selection_key, identity, item, checked)
        seen[index] = checked


def select_group(state, key, items, widgets, checked):
    selected = dict(state.get(key, {}))
    for identity, item in items.items():
        if checked:
            selected.setdefault(identity, item)
        else:
            selected.pop(identity, None)
        if identity in widgets:
            state[widgets[identity]] = checked
    state[key] = selected
