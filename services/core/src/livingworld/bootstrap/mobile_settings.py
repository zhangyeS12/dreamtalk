"""Android managed model scopes and encrypted media credentials. No provider probes."""

from __future__ import annotations

import copy
import json
from uuid import UUID, uuid4


def credentials_for(settings):
    for entry in [
        settings,
        settings.get("scheduler", {}),
        *settings.get("worlds", {}).values(),
        *settings.get("world_schedulers", {}).values(),
    ]:
        if entry.get("secret") and entry.get("secret_ref"):
            yield None, entry["secret_ref"], entry["secret"]
    for reference, entry in settings.get("media_credentials", {}).items():
        yield entry["world"], reference, entry["secret"]


def document(settings, single):
    if not any(settings.get(k) for k in ("worlds", "scheduler", "world_schedulers")):
        return single(settings)
    return {
        "version": 2,
        "default": single(settings),
        "worlds": {k: single(v) for k, v in settings.get("worlds", {}).items()},
        "scheduler": {
            "default": single(settings["scheduler"]) if settings.get("scheduler") else None,
            "worlds": {k: single(v) for k, v in settings.get("world_schedulers", {}).items()},
        },
    }


def scope(value):
    world = value.get("worldId")
    if world is not None:
        world = str(UUID(world))
    return world


def effective(settings, world, scheduler):
    if scheduler:
        if world and world in settings.get("world_schedulers", {}):
            return settings["world_schedulers"][world], False
        return settings.get("scheduler") or settings, world is not None or not bool(
            settings.get("scheduler")
        )
    if world and world in settings.get("worlds", {}):
        return settings["worlds"][world], False
    return settings, world is not None


def persist(updated, host):
    from livingworld.infrastructure.llm.production_config import load_configuration

    check = host._root / ("model-check-" + str(uuid4()) + ".json")
    try:
        check.write_text(json.dumps(host.production_document(updated)), encoding="utf-8")
        load_configuration(check)
    finally:
        check.unlink(missing_ok=True)
    host._stop_if_idle()
    try:
        host._host.secureWrite(json.dumps(updated))
    except Exception:
        host._start()
        raise ValueError("mobile_secure_store") from None
    host._settings = updated
    host._connection()


def dispatch_settings(operation, value, host):
    if operation.startswith("managed_") and operation.endswith("_model_setup"):
        scheduler = operation == "managed_scheduler_model_setup"
        entry, inherited = effective(host._settings, scope(value), scheduler)
        setup = entry.get("setup")
        if not setup:
            return True, None
        setup = {**setup, "inherited": inherited}
        setup["provider_kind"] = {
            "anthropic-messages": "anthropic",
            "gemini-interactions": "gemini",
        }.get(setup["provider_kind"], setup["provider_kind"])
        return True, setup
    if operation in {
        "configure_chat_model",
        "update_chat_model",
        "repair_chat_model",
        "configure_scheduler_model",
        "use_default_chat_model",
        "use_default_scheduler_model",
    }:
        updated = copy.deepcopy(host._settings)
        world = scope(value)
        scheduler = "scheduler" in operation
        key = "world_schedulers" if scheduler else "worlds"
        if operation.startswith("use_default"):
            if world:
                updated.setdefault(key, {}).pop(world, None)
            elif scheduler:
                updated.pop("scheduler", None)
            else:
                raise ValueError("mobile_invalid")
        else:
            explicit = (
                updated.get(key, {}).get(world)
                if world
                else updated.get("scheduler")
                if scheduler
                else updated
                if updated.get("setup")
                else None
            )
            previous = explicit or effective(updated, world, scheduler)[0]
            setup = dict(value["setup"])
            setup["provider_kind"] = {
                "anthropic": "anthropic-messages",
                "gemini": "gemini-interactions",
            }.get(setup["provider_kind"], setup["provider_kind"])
            setup["streaming"] = False if scheduler else value.get("streaming", True)
            setup["secret"] = value.get("secret", "")
            prior = previous.get("setup", {})
            if (
                not setup.get("secret")
                and prior
                and (
                    setup["provider_kind"] != prior["provider_kind"]
                    or setup.get("base_url") != prior.get("base_url")
                )
            ):
                raise ValueError("model_update_new_secret_required")
            previous = dict(previous)
            if explicit is None:
                # An independent scope must never overwrite an inherited key's UUID.
                previous["secret_ref"] = str(uuid4())
            entry = host.validate_model(setup, previous)
            if world:
                updated.setdefault(key, {})[world] = entry
            elif scheduler:
                updated["scheduler"] = entry
            else:
                updated.update(entry)
        persist(updated, host)
        return True, {"old_credential_cleanup_incomplete": False}
    if operation in {"speech_credential_put", "media_credential_put"}:
        world, reference = str(UUID(value["worldId"])), str(UUID(value["secretRef"]))
        secret = value["secret"]
        if not isinstance(secret, str) or not secret.strip() or len(secret.encode()) > 4096:
            raise ValueError("mobile_invalid")
        updated = copy.deepcopy(host._settings)
        bank = updated.setdefault("media_credentials", {})
        if reference in bank and bank[reference]["world"] != world:
            raise ValueError("mobile_invalid")
        bank[reference] = {"world": world, "secret": secret}
        host._host.secureWrite(json.dumps(updated))
        host._settings = updated
        if host._credentials:
            from livingworld.application.llm_config import SecretRef

            host._credentials.upsert_media(UUID(world), SecretRef(UUID(reference)), secret)
        return True, None
    if operation in {"forget_speech_credentials", "forget_media_credentials"}:
        import sqlite3

        world = str(UUID(value["worldId"]))
        reference = str(UUID(value["secretRef"])) if value.get("secretRef") else None
        keep = str(UUID(value["keepSecretRef"])) if value.get("keepSecretRef") else None
        host._stop_if_idle()
        try:
            database = host._root / "data/runtime.sqlite3"
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
                used = set()
                for table in ("speech_settings", "chat_media_settings"):
                    for (raw,) in connection.execute("select settings_json from " + table):
                        item = json.loads(raw)
                        if item.get("secret_ref"):
                            used.add(str(UUID(item["secret_ref"])))
            updated = copy.deepcopy(host._settings)
            bank = updated.get("media_credentials", {})
            for key, entry in list(bank.items()):
                if (
                    entry["world"] == world
                    and key != keep
                    and key not in used
                    and (reference is None or key == reference)
                ):
                    del bank[key]
            host._host.secureWrite(json.dumps(updated))
            host._settings = updated
        finally:
            host._connection()
        return True, None
    return False, None
