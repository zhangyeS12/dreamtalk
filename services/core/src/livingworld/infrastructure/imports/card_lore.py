"""Input-only defaults for embedded books; unusable entries stay in source evidence."""

from copy import deepcopy

from livingworld.application.imports import ImportWarning


def normalize_book(book: dict, *, v3: bool, warnings: list[ImportWarning]) -> dict:
    result = deepcopy(book)

    def default(target: dict, key: str, value: object, path: str) -> None:
        if target.get(key) is None:
            target[key] = value
            warnings.append(
                ImportWarning(
                    "character_card_book_field_normalized",
                    "Embedded book default applied; source retained.",
                    path,
                )
            )

    for key in ("name", "description"):
        default(result, key, "", f"book.{key}")
    default(result, "extensions", {}, "book.extensions")
    for key in ("scan_depth", "token_budget", "recursive_scanning"):
        if key in result and result[key] is None:
            del result[key]
            warnings.append(
                ImportWarning(
                    "character_card_book_field_normalized",
                    "Unset setting retained in source.",
                    f"book.{key}",
                )
            )
    if result.get("entries") is None:
        default(result, "entries", [], "book.entries")
    if type(result["entries"]) is not list:
        return result
    for index, entry in enumerate(result["entries"]):
        if type(entry) is not dict:
            continue
        path = f"book.entries[{index}]"
        for key, value in (
            ("keys", []),
            ("enabled", True),
            ("insertion_order", 0),
            ("extensions", {}),
        ):
            default(entry, key, value, f"{path}.{key}")
        if v3:
            default(entry, "use_regex", False, f"{path}.use_regex")
        for key in ("keys", "secondary_keys"):
            if key in entry and type(entry[key]) is str and (key == "keys" or not v3):
                entry[key] = [entry[key]]
                warnings.append(
                    ImportWarning(
                        "character_card_book_field_normalized",
                        "Single keyword preserved as one keyword.",
                        f"{path}.{key}",
                    )
                )
            elif key in entry and entry[key] is None:
                default(entry, key, [], f"{path}.{key}")
    return result
