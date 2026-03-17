"""Tests for file utilities module."""

import pytest
from pathlib import Path
from codemap.utils.config import Config
from codemap.utils.file_utils import discover_files, get_language, _get_extensions_for_languages


class TestLanguageDetection:
    """Test language detection from file extensions."""

    @pytest.mark.parametrize("extension,expected_lang", [
        (".cs", "csharp"),
        (".dart", "dart"),
        (".go", "go"),
        (".java", "java"),
        (".rs", "rust"),
        (".sql", "sql"),
    ])
    def test_get_language_missing_extensions(self, extension, expected_lang):
        """Test that previously missing extensions now map correctly."""
        test_file = Path(f"test{extension}")
        detected = get_language(test_file)
        assert detected == expected_lang

    def test_get_extensions_for_languages_missing(self):
        """Test extension mapping for previously missing languages."""
        languages = ["csharp", "dart", "go", "java", "rust", "sql"]
        extensions = _get_extensions_for_languages(languages)

        expected = [".cs", ".dart", ".go", ".java", ".rs", ".sql"]
        for ext in expected:
            assert ext in extensions, f"{ext} not returned for its language"

    def test_discover_files_skips_excluded_directories(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("def main(): pass")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "ignored.py").write_text("def ignored(): pass")

        files = list(discover_files(tmp_path, config=Config(languages=["python"])))

        assert files == [tmp_path / "src" / "main.py"]
