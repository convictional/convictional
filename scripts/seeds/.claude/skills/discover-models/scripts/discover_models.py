#!/usr/bin/env python3

import sys
from collections import defaultdict
from enum import StrEnum

from tortoise import Tortoise

from config.settings import settings


def _format_default(field_desc: dict) -> str:
    default = field_desc["default"]
    if default is None or callable(default):
        return ""
    return str(default)


def _build_model_info(model_cls) -> dict:
    desc = model_cls.describe()
    meta = model_cls._meta
    info = {
        "name": model_cls.__name__,
        "module": model_cls.__module__,
        "required_fields": [],
        "optional_fields": [],
        "required_relations": [],
        "optional_relations": [],
    }

    raw_rel_fields = {f["raw_field"] for f in desc["fk_fields"] + desc["o2o_fields"]}

    for fd in desc["data_fields"]:
        name = fd["name"]
        if name in raw_rel_fields or fd["generated"]:
            continue

        type_str = fd["python_type"]
        if fd["field_type"] == "CharEnumFieldInstance":
            enum_type = meta.fields_map[name].enum_type
            if issubclass(enum_type, StrEnum):
                type_str = f"enum: {', '.join(e.value for e in enum_type)}"

        default_str = _format_default(fd)
        required = fd["default"] is None and not fd["nullable"]
        entry = {"name": name, "type": type_str}
        if default_str:
            entry["default"] = default_str
        (info["required_fields"] if required else info["optional_fields"]).append(entry)

    for fd in desc["fk_fields"]:
        target = fd["python_type"].rsplit(".", 1)[-1]
        rel = {"name": fd["name"], "target": target}
        (info["required_relations"] if not fd["nullable"] else info["optional_relations"]).append(rel)

    for fd in desc["o2o_fields"]:
        target = fd["python_type"].rsplit(".", 1)[-1]
        rel = {"name": fd["name"], "target": target, "one_to_one": True}
        (info["required_relations"] if not fd["nullable"] else info["optional_relations"]).append(rel)

    return info


def _get_all_models() -> list[dict]:
    result = []
    for app_name, models in Tortoise.apps.items():
        if app_name == "migrations":
            continue
        for model_cls in models.values():
            if not getattr(model_cls.Meta, "abstract", False):
                result.append(_build_model_info(model_cls))
    return result


def _filter_models(all_info: list[dict], names: list[str]) -> list[dict]:
    results = []
    for name in names:
        lower = name.lower()
        matches = [m for m in all_info if lower == m["name"].lower()]
        if not matches:
            matches = [m for m in all_info if lower in m["name"].lower()]
        results.extend(m for m in matches if m not in results)
    if not results:
        print(f"No models matching: {', '.join(names)}")
    return results


def _topological_sort(models_info: list[dict]) -> list[str]:
    names = {m["name"] for m in models_info}
    deps = {
        m["name"]: {r["target"] for r in m["required_relations"] if r["target"] in names and r["target"] != m["name"]}
        for m in models_info
    }
    ordered = []
    visited: set[str] = set()

    def visit(name: str):
        if name in visited:
            return
        visited.add(name)
        for dep in deps.get(name, ()):
            visit(dep)
        ordered.append(name)

    for name in sorted(deps):
        visit(name)
    return ordered


def _print_list(all_info: list[dict]):
    by_module: dict[str, list[str]] = defaultdict(list)
    for m in all_info:
        by_module[m["module"]].append(m["name"])
    for module in sorted(by_module):
        print(f"\n{module}:")
        for name in sorted(by_module[module]):
            print(f"  {name}")


def _print_show(models: list[dict]):
    if len(models) > 1:
        order = _topological_sort(models)
        info_by_name = {m["name"]: m for m in models}
        print("Creation order:")
        for i, name in enumerate(order, 1):
            m = info_by_name.get(name)
            if m:
                deps = [r["target"] for r in m["required_relations"] if r["target"] != name]
                deps_str = f" (requires: {', '.join(deps)})" if deps else ""
                print(f"  {i}. {name}{deps_str}")
        print()

    for m in models:
        print(f"## {m['name']}")
        if m["required_fields"] or m["required_relations"]:
            print("\nRequired:")
            for f in m["required_fields"]:
                print(f"  {f['name']} ({f['type']})")
            for rel in m["required_relations"]:
                o2o = ", one-to-one" if rel.get("one_to_one") else ""
                print(f"  {rel['name']} -> {rel['target']}{o2o}")

        if m["optional_fields"] or m["optional_relations"]:
            print("\nOptional:")
            for f in m["optional_fields"]:
                default = f" [default: {f['default']}]" if f.get("default") else ""
                print(f"  {f['name']} ({f['type']}){default}")
            for rel in m["optional_relations"]:
                o2o = ", one-to-one" if rel.get("one_to_one") else ""
                print(f"  {rel['name']} -> {rel['target']}{o2o}")
        print()


def main():
    all_info = _get_all_models()
    names = sys.argv[1:]
    if not names:
        _print_list(all_info)
    else:
        models = _filter_models(all_info, names)
        if models:
            _print_show(models)


if __name__ == "__main__":
    model_paths = settings.tortoise_config["apps"]["convictional"]["models"]
    Tortoise.init_models(model_paths, app_label="convictional")
    main()
