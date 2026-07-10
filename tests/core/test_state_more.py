from pathlib import Path

import pytest

from repo_release_tools.state import (
    _dict_to_toml,
    _toml_value,
    docs_lock_path,
    docs_map_lock_path,
    drift_lock_path,
    tree_manifest_gz_path,
    tree_manifest_path,
)


def test_docs_lock_path_variants(tmp_path: Path) -> None:
    root = tmp_path
    # absolute path returned unchanged
    abs_path = Path("/tmp/some.lock.toml")
    assert docs_lock_path(root, str(abs_path)) == abs_path

    # path starting with .rrt should be joined directly to root
    p = docs_lock_path(root, ".rrt/custom.lock.toml")
    assert p == root / ".rrt" / "custom.lock.toml"

    # default uses .rrt/docs.lock.toml
    assert docs_lock_path(root) == root / ".rrt" / "docs.lock.toml"


def test_docs_map_lock_path_variants(tmp_path: Path) -> None:
    root = tmp_path
    # absolute path returned unchanged
    abs_path = Path("/tmp/some_map.lock.toml")
    assert docs_map_lock_path(root, str(abs_path)) == abs_path

    # path starting with .rrt should be joined directly to root
    p = docs_map_lock_path(root, ".rrt/custom_map.lock.toml")
    assert p == root / ".rrt" / "custom_map.lock.toml"

    # default uses .rrt/docs_map.lock.toml
    assert docs_map_lock_path(root) == root / ".rrt" / "docs_map.lock.toml"


def test_drift_lock_path(tmp_path: Path) -> None:
    assert drift_lock_path(tmp_path) == tmp_path / ".rrt" / "drift.lock.toml"


def test_tree_manifest_paths(tmp_path: Path) -> None:
    assert tree_manifest_path(tmp_path) == tmp_path / ".rrt" / "tree.manifest.json"
    assert tree_manifest_gz_path(tmp_path) == tmp_path / ".rrt" / "tree.manifest.json.gz"


def test_toml_value_basic_types() -> None:
    assert _toml_value(True) == "true"
    assert _toml_value(False) == "false"
    assert _toml_value(5) == "5"
    # floats use repr()
    assert _toml_value(1.5).startswith("1.5")
    assert _toml_value("hi\nthere").startswith('"hi\\nthere"')
    assert _toml_value([1, "a"]) == '[1, "a"]'


def test_toml_value_unsupported_raises() -> None:
    with pytest.raises(TypeError):
        _toml_value({"a": 1})


def test_dict_to_toml_nested_table() -> None:
    data = {
        "meta": {"generated_at": "ts", "rrt_version": "v"},
        "sources": {"src/main.py": {"hash": "sha256:abc", "size": 10}},
    }
    toml = _dict_to_toml(data)
    # nested table key with slash must be quoted
    assert 'sources."src/main.py"' in toml
    assert 'hash = "sha256:abc"' in toml
