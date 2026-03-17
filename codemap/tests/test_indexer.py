"""Tests for the indexer module."""

import json
import pytest
from pathlib import Path

import codemap.core.indexer as indexer_module
from codemap.core.hasher import hash_file
from codemap.core.indexer import Indexer
from codemap.core.map_store import MapStore


class TestIndexer:
    """Tests for Indexer class."""

    def test_index_single_file(self, tmp_path: Path):
        # Create a sample Python file
        (tmp_path / "service.py").write_text('''
class UserService:
    """User service class."""

    def get_user(self, id: int) -> dict:
        """Get a user by ID."""
        pass

    def create_user(self, name: str) -> dict:
        """Create a new user."""
        pass
''')

        indexer = Indexer(root=tmp_path)
        result = indexer.index_all()

        assert result["total_files"] == 1
        assert result["total_symbols"] == 3  # 1 class + 2 methods

        # Verify .codemap directory created
        codemap_dir = tmp_path / ".codemap"
        assert codemap_dir.exists()

        # Verify manifest exists
        manifest_path = codemap_dir / ".codemap.json"
        assert manifest_path.exists()

        # Verify content via MapStore
        store = MapStore.load(tmp_path)
        entry = store.get_file("service.py")
        assert entry is not None
        assert entry.language == "python"
        assert len(entry.symbols) == 1  # Just the class at top level

    def test_index_multiple_files(self, tmp_path: Path):
        # Create multiple Python files
        (tmp_path / "module1.py").write_text('''
def func1():
    pass
''')
        (tmp_path / "module2.py").write_text('''
def func2():
    pass

class Class1:
    pass
''')

        indexer = Indexer(root=tmp_path)
        result = indexer.index_all()

        assert result["total_files"] == 2
        assert result["total_symbols"] == 3

    def test_index_nested_directories(self, tmp_path: Path):
        """Test that files in nested directories are indexed properly."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "components").mkdir()
        (tmp_path / "src" / "main.py").write_text("def main(): pass")
        (tmp_path / "src" / "components" / "button.py").write_text("class Button: pass")

        indexer = Indexer(root=tmp_path)
        result = indexer.index_all()

        assert result["total_files"] == 2

        # Verify distributed structure
        codemap_dir = tmp_path / ".codemap"
        assert (codemap_dir / "src" / ".codemap.json").exists()
        assert (codemap_dir / "src" / "components" / ".codemap.json").exists()

        # Verify files can be retrieved
        store = MapStore.load(tmp_path)
        assert store.get_file("src/main.py") is not None
        assert store.get_file("src/components/button.py") is not None

    def test_index_respects_exclude_patterns(self, tmp_path: Path):
        # Create files in different directories
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("def main(): pass")

        (tmp_path / "venv").mkdir()
        (tmp_path / "venv" / "lib.py").write_text("def lib(): pass")

        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "cache.py").write_text("def cache(): pass")

        indexer = Indexer(root=tmp_path)
        result = indexer.index_all()

        # Should only index src/main.py
        assert result["total_files"] == 1

    def test_index_filters_by_language(self, tmp_path: Path):
        (tmp_path / "script.py").write_text("def py(): pass")
        (tmp_path / "script.js").write_text("function js() {}")

        indexer = Indexer(root=tmp_path, languages=["python"])
        result = indexer.index_all()

        assert result["total_files"] == 1

    def test_update_file(self, tmp_path: Path):
        # Create and index a file
        test_file = tmp_path / "test.py"
        test_file.write_text('''
def original():
    pass
''')

        indexer = Indexer(root=tmp_path)
        indexer.index_all()

        # Modify the file
        test_file.write_text('''
def original():
    pass

def new_function():
    pass
''')

        # Update the index
        result = indexer.update_file(test_file)
        assert result["symbols_changed"] == 1

        # Verify the update
        store = MapStore.load(tmp_path)
        entry = store.get_file("test.py")
        assert len(entry.symbols) == 2

    def test_update_file_in_subdirectory(self, tmp_path: Path):
        """Test updating a file in a subdirectory."""
        (tmp_path / "src").mkdir()
        test_file = tmp_path / "src" / "module.py"
        test_file.write_text("def func1(): pass")

        indexer = Indexer(root=tmp_path)
        indexer.index_all()

        # Modify
        test_file.write_text("def func1(): pass\ndef func2(): pass")

        result = indexer.update_file(test_file)
        assert result["symbols_changed"] == 1

        store = MapStore.load(tmp_path)
        entry = store.get_file("src/module.py")
        assert len(entry.symbols) == 2

    def test_update_deleted_file(self, tmp_path: Path):
        # Create and index a file
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        indexer = Indexer(root=tmp_path)
        indexer.index_all()

        # Delete the file
        test_file.unlink()

        # Update should remove from index
        result = indexer.update_file(test_file)
        assert result["removed"]

        store = MapStore.load(tmp_path)
        assert store.get_file("test.py") is None

    def test_validate_all_fresh(self, tmp_path: Path):
        (tmp_path / "test.py").write_text("def func(): pass")

        indexer = Indexer(root=tmp_path)
        indexer.index_all()

        # No changes, should be empty
        stale = indexer.validate_all()
        assert stale == []

    def test_validate_all_stale(self, tmp_path: Path):
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        indexer = Indexer(root=tmp_path)
        indexer.index_all()

        # Modify the file
        test_file.write_text("def func(): pass  # modified")

        stale = indexer.validate_all()
        assert "test.py" in stale

    def test_validate_file(self, tmp_path: Path):
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        indexer = Indexer(root=tmp_path)
        indexer.index_all()

        # Fresh file
        assert indexer.validate_file("test.py")

        # Modify
        test_file.write_text("def modified(): pass")
        assert not indexer.validate_file("test.py")

    def test_load_existing(self, tmp_path: Path):
        (tmp_path / "test.py").write_text("def func(): pass")

        # Create initial index
        indexer1 = Indexer(root=tmp_path)
        indexer1.index_all()

        # Load existing
        indexer2 = Indexer.load_existing(tmp_path)
        assert list(indexer2.map_store.get_all_files())

    def test_load_existing_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            Indexer.load_existing(tmp_path)

    def test_handles_syntax_error_gracefully(self, tmp_path: Path):
        # Create a file with syntax error
        (tmp_path / "broken.py").write_text('''
def broken(
    missing paren
''')
        (tmp_path / "valid.py").write_text("def valid(): pass")

        indexer = Indexer(root=tmp_path)
        result = indexer.index_all()

        # Both files are indexed, but broken.py has no symbols
        assert result["total_files"] == 2
        # Verify valid file has symbols
        assert result["total_symbols"] >= 1

        # Verify the broken file was indexed but with no symbols
        store = indexer.map_store
        broken_entry = store.get_file("broken.py")
        assert broken_entry is not None
        assert len(broken_entry.symbols) == 0  # No symbols extracted due to syntax error

        valid_entry = store.get_file("valid.py")
        assert valid_entry is not None
        assert len(valid_entry.symbols) == 1

    def test_handles_encoding_error(self, tmp_path: Path):
        # Create a file with invalid UTF-8
        test_file = tmp_path / "binary.py"
        test_file.write_bytes(b"def func(): pass\n\x80\x81\x82")

        indexer = Indexer(root=tmp_path)
        result = indexer.index_all()

        # Should handle gracefully
        assert result["total_files"] == 1

    def test_index_all_avoids_extra_disk_reads(self, tmp_path: Path, monkeypatch):
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        def fail_read_text(*args, **kwargs):
            raise AssertionError("index_all should not call Path.read_text")

        def fail_hash_file(*args, **kwargs):
            raise AssertionError("index_all should hash the already-read bytes")

        monkeypatch.setattr(Path, "read_text", fail_read_text)
        monkeypatch.setattr(indexer_module, "hash_file", fail_hash_file)

        indexer = Indexer(root=tmp_path)
        result = indexer.index_all()

        assert result["total_files"] == 1

    def test_validate_all_skips_hash_when_metadata_matches(self, tmp_path: Path, monkeypatch):
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        indexer = Indexer(root=tmp_path)
        indexer.index_all()

        def fail_hash_file(*args, **kwargs):
            raise AssertionError("validate_all should not hash unchanged files")

        monkeypatch.setattr(indexer_module, "hash_file", fail_hash_file)

        assert indexer.validate_all() == []

    def test_migrate_missing_file_metadata(self, tmp_path: Path):
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        store = MapStore(tmp_path)
        store.set_metadata(str(tmp_path), {"languages": ["python"]})
        store.update_file("test.py", hash_file(test_file), "python", 1, symbols=[])
        store.update_stats()
        store.save()

        indexer = Indexer.load_existing(tmp_path)
        result = indexer.migrate_missing_file_metadata()

        assert result["migrated"] == 1

        entry = MapStore.load(tmp_path).get_file("test.py")
        assert entry is not None
        assert entry.size == test_file.stat().st_size
        assert entry.mtime_ns == test_file.stat().st_mtime_ns

    def test_migrate_missing_file_metadata_skips_stale_files(self, tmp_path: Path):
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        store = MapStore(tmp_path)
        store.set_metadata(str(tmp_path), {"languages": ["python"]})
        store.update_file("test.py", "abc123def456", "python", 1, symbols=[])
        store.update_stats()
        store.save()

        test_file.write_text("def modified(): pass")

        indexer = Indexer.load_existing(tmp_path)
        result = indexer.migrate_missing_file_metadata()

        assert result["migrated"] == 0
        assert result["stale"] == 1

        entry = MapStore.load(tmp_path).get_file("test.py")
        assert entry is not None
        assert entry.size is None
        assert entry.mtime_ns is None

    def test_update_all_stale(self, tmp_path: Path):
        (tmp_path / "file1.py").write_text("def f1(): pass")
        (tmp_path / "file2.py").write_text("def f2(): pass")

        indexer = Indexer(root=tmp_path)
        indexer.index_all()

        # Modify both files
        (tmp_path / "file1.py").write_text("def f1_modified(): pass")
        (tmp_path / "file2.py").write_text("def f2_modified(): pass")

        result = indexer.update_all_stale()
        assert result["updated"] == 2

    def test_update_all_stale_saves_once(self, tmp_path: Path, monkeypatch):
        (tmp_path / "file1.py").write_text("def f1(): pass")
        (tmp_path / "file2.py").write_text("def f2(): pass")

        indexer = Indexer(root=tmp_path)
        indexer.index_all()

        (tmp_path / "file1.py").write_text("def f1_modified(): pass")
        (tmp_path / "file2.py").write_text("def f2_modified(): pass")

        save_calls = 0
        original_save = indexer.map_store.save

        def counted_save():
            nonlocal save_calls
            save_calls += 1
            return original_save()

        monkeypatch.setattr(indexer.map_store, "save", counted_save)

        result = indexer.update_all_stale()

        assert result["updated"] == 2
        assert save_calls == 1

    def test_reindex_clears_previous(self, tmp_path: Path):
        """Test that re-running index_all clears previous index."""
        (tmp_path / "file1.py").write_text("def f1(): pass")

        indexer = Indexer(root=tmp_path)
        indexer.index_all()

        # Remove file1.py and add file2.py
        (tmp_path / "file1.py").unlink()
        (tmp_path / "file2.py").write_text("def f2(): pass")

        # Re-index
        indexer.index_all()

        store = MapStore.load(tmp_path)
        files = list(store.get_all_files())

        # Should only have file2.py
        assert len(files) == 1
        assert files[0][0] == "file2.py"
