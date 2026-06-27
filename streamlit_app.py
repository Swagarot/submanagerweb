"""
Expense Manager — Streamlit front-end

This file provides a web UI for the original CLI app using Streamlit.

Notes for reading the code:
- Streamlit functions (e.g. `st.button`, `st.form`, `st.session_state`) are
    high-level UI primitives that register widgets and callbacks. They do not
    block like `input()` in a CLI; instead Streamlit reruns the script on
    interaction and preserves state in `st.session_state`.

    Example comparison:
    - CLI prompt: `name = input("Enter name: ")`  # blocks until user types
    - Streamlit: `name = st.text_input("Name")`  # renders a text box; value
        is available immediately and the script reruns when it changes

    - CLI wait-for-choice: `choice = int(input("Choice: "))`
    - Streamlit choice: `if st.button("Delete"):` -> registers a click
        callback; use `on_click=` to call a function instead of blocking.

Design decisions:
- Keep data in-memory in `st.session_state.expenses` (same structure as CLI).
- Use simple indices for operations (edit/delete/duplicate) to avoid adding
    persistent IDs to items.

"""

import streamlit as st
import json
import os
import pandas as pd
import io
import urllib.request

import dummy_manager

st.set_page_config(page_title="Expense Manager Web", page_icon="🎫")

EXPENSE_TYPE_OPTIONS = ["One-time", "Monthly", "Yearly","Digital/Physical Subscription"]

# Path to the JSON file used for persistence. Override with the DATA_FILE
# environment variable (the Docker setup points this at a mounted volume so
# data survives container restarts). Defaults to a file next to this script.
DATA_FILE = os.environ.get(
    "DATA_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "expenses.json"),
)

# Separate path for the dummy/sample dataset. This is read ONLY when the user
# clicks a button in the Dummy Data section — never loaded automatically at
# startup. Override with the DUMMY_FILE environment variable.
DUMMY_FILE = os.environ.get(
    "DUMMY_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dummydata.json"),
)

DEFAULT_EXPENSES = {
    "Housing": [],
    "Food": [],
    "Transportation": [],
    "Utilities": [],
    "Miscellaneous": [],
}


def load_expenses():
    """Load the expenses dict from DATA_FILE, or return defaults if missing.

    Called once at startup. Any read/parse error falls back to the empty
    default structure so the app always starts in a usable state.
    """
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {k: list(v) for k, v in DEFAULT_EXPENSES.items()}


def save_expenses():
    """Write the current expenses to DATA_FILE atomically.

    We write to a temp file then replace, so a crash mid-write can't corrupt
    the existing data file.
    """
    try:
        os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st.session_state.expenses, f, indent=2, ensure_ascii=False)
        os.replace(tmp, DATA_FILE)
    except OSError as e:
        st.warning(f"Could not save data to {DATA_FILE}: {e}")


def load_dummy():
    """Load the dummy dataset from DUMMY_FILE.

    Falls back to the hardcoded `dummy_manager.dummy_data` if the file is
    missing or invalid, so the dummy buttons always work. Returns None only if
    nothing usable is available.
    """
    try:
        with open(DUMMY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return dummy_manager.dummy_data


@st.cache_data(ttl=300)
def get_live_exchange_rates():
    """Fetch live USD/ILS and EUR/ILS exchange rates."""
    url = "https://open.er-api.com/v6/latest/ILS"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}")
            raw = response.read().decode("utf-8")
            data = json.loads(raw)
        if data.get("result") != "success":
            raise ValueError(f"API result not success: {data}")
        rates = data.get("rates", {})
        usd_rate = rates.get("USD")
        eur_rate = rates.get("EUR")
        if usd_rate is None or eur_rate is None:
            raise ValueError(f"Missing rate data: {rates}")
        return {
            "USD": usd_rate,
            "EUR": eur_rate,
            "source": data.get("base_code", "ILS"),
            "date": data.get("time_last_update_utc"),
            "error": None,
        }
    except Exception as e:
        return {
            "USD": 0.27,
            "EUR": 0.25,
            "source": "fallback",
            "date": None,
            "error": str(e),
            "fallback": True,
        }
    
def ensure_state():
    """Ensure required keys exist in `st.session_state`.

    Streamlit preserves `st.session_state` across reruns. This replaces
    global variables / module-level state you'd use in a normal script.
    """
    if "expenses" not in st.session_state:
        st.session_state.expenses = load_expenses()
    # No persistent page state needed: the UI uses native Streamlit tabs.


def expenses_to_df(expenses):
    """Convert the nested `expenses` dict into a pandas.DataFrame.

    This is used for the View table. In a CLI you'd format strings and
    print them; here we prefer a DataFrame for convenient sorting/filtering.
    """
    rows = []
    for category, items in expenses.items():
        for item in items:
            rows.append({
                "category": category,
                "name": item.get("name"),
                "type": item.get("type"),
                "cost": item.get("cost"),
            })
    return pd.DataFrame(rows)

def subs_to_df(expenses):
    """Convert the nested `expenses` dict into a pandas.DataFrame. (only subscriptions types)

    This is used for the View table. In a CLI you'd format strings and
    print them; here we prefer a DataFrame for convenient sorting/filtering.
    """
    rows = []
    for category, items in expenses.items():
        for item in items:
            if item.get("type") in ["Digital/Physical Subscription"]:
                rows.append({
                    "category": category,
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "cost": item.get("cost"),
                    "url": item.get("url", ""),
                })
    return pd.DataFrame(rows)



def add_expense(name, cost, type_, category, selected, rates, url=None):
    """Add an expense dict to the given `category` list.

    Equivalent CLI action: collect values via `input()` then append to list.
    Streamlit version appends directly to `st.session_state.expenses` and the
    UI will update on the next rerun.
    """
    if selected == "Dollar($)" and rates.get("USD") is not None:
        cost = float(cost) / rates["USD"]
    elif selected == "Euro(€)" and rates.get("EUR") is not None:
        cost = float(cost) / rates["EUR"]
    cost = round(float(cost), 2)
    sub = {"name": name, "cost": cost, "type": type_, "url": url}
    st.session_state.expenses[category].append(sub)


def delete_expense(category, index):
    """Remove the item at `index` from `category`.

    Uses list.pop(index) which mutates the list in place. The function
    swallows exceptions so UI callbacks won't crash the app; consider
    validating index if you prefer raising errors.
    """
    try:
        st.session_state.expenses[category].pop(index)
    except Exception:
        pass


def request_delete(category, index):
    """Request deletion by storing a pending confirmation in state.

    Instead of deleting immediately, we set `pending_delete`. The UI shows
    a confirm/cancel prompt. This avoids accidental deletes and gives the
    user a chance to cancel.
    """
    st.session_state.pending_delete = {"category": category, "index": index}


def cancel_delete():
    if "pending_delete" in st.session_state:
        del st.session_state["pending_delete"]


def confirm_delete():
    pd = st.session_state.get("pending_delete")
    if pd:
        delete_expense(pd["category"], pd["index"])
        del st.session_state["pending_delete"]


def _sync_add_type():
    st.session_state["_add_type_val"] = st.session_state["add-type"]


def _sync_edit_type():
    st.session_state["_edit_type_val"] = st.session_state["edit-type"]


def request_edit(category, index):
    """Start editing: mark `pending_edit` with the target location.

    The edit form is rendered when `pending_edit` exists. This keeps the
    edit UI separate from the per-row buttons.
    """
    item = st.session_state.expenses[category][index]
    st.session_state["_edit_type_val"] = item.get("type", EXPENSE_TYPE_OPTIONS[0])
    st.session_state.pending_edit = {"category": category, "index": index}


def cancel_edit():
    if "pending_edit" in st.session_state:
        del st.session_state["pending_edit"]


def save_edit(name, cost, type_, new_category, url=""):
    """Save edits from the edit form into `st.session_state.expenses`.

    If the category changed, the item is removed from the old category and
    appended to the new category (mirrors a 'move' operation).
    """
    pd = st.session_state.get("pending_edit")
    if not pd:
        return
    old_cat = pd["category"]
    idx = pd["index"]
    updated = {"name": name, "cost": round(float(cost), 2), "type": type_, "url": url}
    if new_category == old_cat:
        try:
            st.session_state.expenses[old_cat][idx] = updated
        except Exception:
            pass
    else:
        try:
            st.session_state.expenses[old_cat].pop(idx)
        except Exception:
            pass
        st.session_state.expenses[new_category].append(updated)
    del st.session_state["pending_edit"]


def duplicate_expense(category, index, new_name):
    item = st.session_state.expenses[category][index].copy()
    item["name"] = new_name
    st.session_state.expenses[category].append(item)


def replace_with_dummy():
    """Replace current data with the dummy dataset from DUMMY_FILE.

    Only runs when the user clicks the button in the Dummy Data section.
    CLI analog: reassigning the `expenses` variable to the dummy dict.
    """
    dummy = load_dummy()
    st.session_state.expenses.clear()
    st.session_state.expenses.update({k: [item.copy() for item in v] for k, v in dummy.items()})


def append_dummy():
    dummy = load_dummy()
    for category, items in dummy.items():
        st.session_state.expenses.setdefault(category, [])
        st.session_state.expenses[category].extend([item.copy() for item in items])


def do_replace_with_dummy():
    replace_with_dummy()
    st.session_state.dummy_action = "replaced"


def do_append_dummy():
    append_dummy()
    st.session_state.dummy_action = "appended"





def save_to_bytes():
    """Serialize `expenses` to JSON bytes for download.

    In a CLI you'd write to a file with `open(filename, 'w')` and
    `json.dump(expenses, f)`. Streamlit offers `st.download_button` to serve
    the bytes to the browser without writing a file on the server.
    """
    return json.dumps(st.session_state.expenses, indent=2).encode("utf-8")


def load_from_json_bytes(b):
    loaded = json.load(io.BytesIO(b))
    st.session_state.expenses.clear()
    st.session_state.expenses.update(loaded)


def calc_month(expenses):
    """Return (monthly_count, monthly_total_including_amortized_yearly/one-time)."""
    count_month = 0
    monthtotal = 0
    for items in expenses.values():
        for item in items:
            item_type = item.get("type")
            cost = item.get("cost", 0)
            if item_type == "Monthly":
                count_month += 1
                monthtotal += cost
            elif item_type == "Yearly":
                monthtotal += (cost / 12)
            else:
                monthtotal += (cost / 12)
    return count_month, round(monthtotal, 2)


def calc_year(expenses):
    yeartotal = 0
    count_year = 0
    for items in expenses.values():
        for item in items:
            item_type = item.get("type")
            cost = item.get("cost", 0)
            if item_type == "Yearly":
                count_year += 1
                yeartotal += (cost * 12)
            elif item_type == "Monthly":
                yeartotal += (cost * 12)
            else:
                yeartotal += cost
    return count_year, round(yeartotal, 2)


def count_type_by_cat(expenses):
    category_count_month = {}
    category_count_year = {}
    category_count_one_time = {}
    for category, items in expenses.items():
        count_month = 0
        count_year = 0
        count_one = 0
        for item in items:
            item_type = item.get("type")
            if item_type == "Monthly":
                count_month += 1
            elif item_type == "Yearly":
                count_year += 1
            else:
                count_one += 1
        category_count_month[category] = count_month
        category_count_year[category] = count_year
        category_count_one_time[category] = count_one
    return category_count_year, category_count_month, category_count_one_time


def main():
    ensure_state()
    st.title("Expense Manager — Web")
    st.markdown("""
    <style>
    div[data-testid="stForm"] { border: none !important; padding: 0 !important; box-shadow: none !important; }
    </style>
    """, unsafe_allow_html=True)

    # Native Streamlit tabs provide the page navigation.
    # Ensure the `pages` list includes labels for all tab indices used below
    pages = [
        "Manage",
        "View",
        "Summary",
        "Storage",
        "Subscription Manager",
        "Dummy Data Options",
    ]
    tabs = st.tabs(pages)

    with tabs[0]:
        st.header("Add Expense")
        if "_add_type_val" not in st.session_state:
            st.session_state["_add_type_val"] = EXPENSE_TYPE_OPTIONS[0]
        with st.container(border=True):
            st.selectbox("Type", EXPENSE_TYPE_OPTIONS, key="add-type", on_change=_sync_add_type)
            add_type = st.session_state["_add_type_val"]
            with st.form("add_expense"):
                name = st.text_input("Name", key="add-name")
                cost = st.number_input("Cost", min_value=0.0, format="%.2f", key="add-cost")
                category = st.selectbox("Category", list(st.session_state.expenses.keys()), key="add-category")
                currency = ["Shekel(₪)", "Dollar($)", "Euro(€)"]
                selected = st.selectbox("Which Currency?", currency, key="add-currency")
                if add_type == "Digital/Physical Subscription":
                    url = st.text_input("Subscription URL (optional)", key="add-url", placeholder="https://...")
                else:
                    url = ""
                rates = get_live_exchange_rates()
                submitted = st.form_submit_button("Add", key="add-submit")
                if submitted:
                    add_expense(name, cost, add_type, category, selected, rates, url=url)
                    st.success("Added")

        st.header("Existing Expenses")
        # show delete confirmation if requested
        if "pending_delete" in st.session_state:
            pd = st.session_state.pending_delete
            st.warning(f"Delete '{st.session_state.expenses[pd['category']][pd['index']]['name']}' from {pd['category']}?")
            c1, c2 = st.columns(2)
            c1.button("Confirm Delete", on_click=confirm_delete, key="confirm-delete")
            c2.button("Cancel", on_click=cancel_delete, key="cancel-delete")

        # show edit form if requested
        if "pending_edit" in st.session_state:
            pe = st.session_state.pending_edit
            try:
                edit_item = st.session_state.expenses[pe['category']][pe['index']]
            except Exception:
                cancel_edit()
            else:
                st.subheader("Edit Expense")
                with st.container(border=True):
                    current_type = edit_item.get('type', 'Monthly')
                    edit_type = st.session_state.get("_edit_type_val", current_type)
                    type_index = EXPENSE_TYPE_OPTIONS.index(edit_type) if edit_type in EXPENSE_TYPE_OPTIONS else 0
                    st.selectbox("Type", EXPENSE_TYPE_OPTIONS, index=type_index, key="edit-type", on_change=_sync_edit_type)
                    with st.form("edit_expense"):
                        name = st.text_input("Name", value=edit_item.get('name',''), key="edit-name")
                        cost = st.number_input("Cost", value=float(edit_item.get('cost',0.0)), format="%.2f", key="edit-cost")
                        cats = list(st.session_state.expenses.keys())
                        cat_index = cats.index(pe['category']) if pe['category'] in cats else 0
                        new_category = st.selectbox("Category", cats, index=cat_index, key="edit-category")
                        if edit_type == "Digital/Physical Subscription":
                            url = st.text_input("Subscription URL (optional)", value=edit_item.get('url', ''), key="edit-url", placeholder="https://...")
                        else:
                            url = ""
                        submitted = st.form_submit_button("Save", key="edit-submit")
                        if submitted:
                            save_edit(name, cost, edit_type, new_category, url=url)
                            st.success("Saved")
                if st.button("Cancel Edit", on_click=cancel_edit, key="cancel-edit"):
                    pass

        for category, items in st.session_state.expenses.items():
            with st.expander(f"{category} ({len(items)})"):
                # iterate over a snapshot to avoid mutation during iteration
                for i, item in enumerate(list(items)):
                    cols = st.columns([3, 1, 1, 1])
                    url = item.get('url', '')
                    if url:
                        cols[0].markdown(f"**{item['name']}** — {item['type']} — ₪{item['cost']} — [Visit]({url})")
                    else:
                        cols[0].write(f"**{item['name']}** — {item['type']} — ₪{item['cost']}")
                    cols[1].button("Edit", key=f"edit-{category}-{i}", on_click=request_edit, args=(category, i))
                    cols[2].button("Delete", key=f"del-{category}-{i}", on_click=request_delete, args=(category, i))
                    new_name = item['name'] + " (copy)"
                    cols[3].button("Duplicate", key=f"dup-{category}-{i}", on_click=duplicate_expense, args=(category, i, new_name))

    with tabs[1]:
        st.header("View / Search / Filter")
        df = expenses_to_df(st.session_state.expenses)
        if df.empty:
            st.info("No expenses yet")
        else:
            cols = st.columns(3)
            cat_options = ["All"] + list(st.session_state.expenses.keys())
            cat = cols[0].selectbox("Category", cat_options, key="view-category")
            typ = cols[1].selectbox("Type", ["All"] + EXPENSE_TYPE_OPTIONS, key="view-type")
            sort = cols[2].selectbox("Sort by", ["None", "Cost Asc", "Cost Desc"], key="view-sort")

            search = st.text_input("Search name", key="view-search")

            df2 = df.copy()
            if cat != "All":
                df2 = df2[df2["category"] == cat]
            if typ != "All":
                df2 = df2[df2["type"] == typ]
            if search:
                df2 = df2[df2["name"].str.contains(search, case=False, na=False)]
            if sort == "Cost Asc":
                df2 = df2.sort_values("cost")
            if sort == "Cost Desc":
                df2 = df2.sort_values("cost", ascending=False)

            st.dataframe(df2.reset_index(drop=True), hide_index=True)

    with tabs[2]:
        st.header("Summary / Totals")
        month_count, month_total = calc_month(st.session_state.expenses)
        year_count, year_total = calc_year(st.session_state.expenses)
        cat_year, cat_month, cat_one = count_type_by_cat(st.session_state.expenses)
        one_time_count = sum(cat_one.values())

        st.metric("Monthly expenses", month_count)
        st.metric("Monthly total (incl. amortized yearly/one-time)", f"₪{month_total:.2f}")
        st.metric("Yearly expenses", year_count)
        st.metric("One-time expenses", one_time_count)
        st.metric("Yearly total", f"₪{year_total:.2f}")

        rates = get_live_exchange_rates()
        st.subheader("Live exchange rates")
        if rates.get("USD") is not None and rates.get("EUR") is not None:
            if rates.get("fallback"):
                st.info(f"Using fallback exchange rates because live fetch failed: {rates.get('error')}")
            st.write(f"1 ILS = {rates['USD']:.4f} USD")
            st.write(f"1 ILS = {rates['EUR']:.4f} EUR")
            target_currency = st.selectbox("Convert totals to", ["ILS", "USD", "EUR"], index=0, key="summary-convert")
            if target_currency == "USD":
                st.metric("Monthly total (USD)", f"${month_total * rates['USD']:.2f}")
                st.metric("Yearly total (USD)", f"${year_total * rates['USD']:.2f}")
            elif target_currency == "EUR":
                st.metric("Monthly total (EUR)", f"€{month_total * rates['EUR']:.2f}")
                st.metric("Yearly total (EUR)", f"€{year_total * rates['EUR']:.2f}")
        else:
            st.warning(f"Could not load exchange rates: {rates.get('error', 'unknown error')}")

        st.subheader("Per-category counts")
        cat_year, cat_month, cat_one = count_type_by_cat(st.session_state.expenses)
        for category in st.session_state.expenses.keys():
            st.write(
                f"{category}: Monthly {cat_month.get(category,0)} | Yearly {cat_year.get(category,0)} | One-time {cat_one.get(category,0)}"
            )

    with tabs[3]:
        st.header("Save / Load JSON")
        b = save_to_bytes()
        st.download_button("Download JSON", data=b, file_name="expenses.json", mime="application/json", key="download-json")

        uploaded = st.file_uploader("Upload JSON to overwrite", type=["json"], key="upload-json")
        if uploaded is not None:
            try:
                load_from_json_bytes(uploaded.read())
                st.success("Loaded")
            except Exception as e:
                st.error(f"Failed to load: {e}")


    with tabs[4]:
        st.header("Subscription Manager")

        all_subs = []
        for _cat, _items in st.session_state.expenses.items():
            for _item in _items:
                if _item.get("type") == "Digital/Physical Subscription":
                    all_subs.append({**_item, "category": _cat})

        if not all_subs:
            st.info("No subscriptions yet. Add one from the Manage tab.")
        else:
            total_cost = sum(s["cost"] for s in all_subs)
            with_url = sum(1 for s in all_subs if s.get("url"))
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Subscriptions", len(all_subs))
            m2.metric("Total Cost", f"₪{total_cost:.2f}")
            m3.metric("With Link", f"{with_url} / {len(all_subs)}")

            st.divider()

            search = st.text_input("Search", key="subs-search", placeholder="Search subscriptions...")
            fc1, fc2 = st.columns(2)
            cat = fc1.selectbox("Category", ["All"] + list(st.session_state.expenses.keys()), key="subs-category")
            sort = fc2.selectbox("Sort by", ["None", "Cost Asc", "Cost Desc", "Name A-Z"], key="subs-sort")

            subs = all_subs.copy()
            if search:
                subs = [s for s in subs if search.lower() in s["name"].lower()]
            if cat != "All":
                subs = [s for s in subs if s["category"] == cat]
            if sort == "Cost Asc":
                subs = sorted(subs, key=lambda x: x["cost"])
            elif sort == "Cost Desc":
                subs = sorted(subs, key=lambda x: x["cost"], reverse=True)
            elif sort == "Name A-Z":
                subs = sorted(subs, key=lambda x: x["name"].lower())

            st.divider()
            for row_start in range(0, len(subs), 3):
                row_subs = subs[row_start:row_start + 3]
                cols = st.columns(3)
                for col, sub in zip(cols, row_subs):
                    with col:
                        with st.container(border=True):
                            st.markdown(f"**{sub['name']}**")
                            st.write(f"₪{sub['cost']:.2f}")
                            st.caption(sub["category"])
                            if sub.get("url"):
                                st.link_button("Visit", sub["url"])


    with tabs[5]:
        st.header("Dummy Data Options")
        st.caption(f"Dummy data is read from: `{DUMMY_FILE}`")
        if os.path.exists(DUMMY_FILE):
            st.info("Dummy data file found. Use a button below to load it.")
        else:
            st.warning("Dummy data file not found — buttons fall back to the built-in sample data.")

        c1, c2 = st.columns(2)
        c1.button("Load dummy data from file (replace)", key="replace_dummy", on_click=do_replace_with_dummy)
        c2.button("Load dummy data from file (append)", key="append_dummy", on_click=do_append_dummy)

        if st.session_state.get("dummy_action") == "replaced":
            st.success("Replaced current data with dummy data from file")
        elif st.session_state.get("dummy_action") == "appended":
            st.success("Appended dummy data from file")

    # Persist after every run. Streamlit reruns the whole script on each
    # interaction, so this reliably captures any add/edit/delete/import.
    save_expenses()


if __name__ == "__main__":
    main()
