# Tests für SearXNG Client

import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import json

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.search.searxng_client import SearXNGClient, SearchResult, SearchUnavailableError


class TestSearXNGClient(unittest.TestCase):
    """Tests für SearXNGClient."""

    def setUp(self):
        """Vorbereitung für Tests."""
        self.client = SearXNGClient()

    @patch("core.search.searxng_client.requests.get")
    def test_successful_search(self, mock_get):
        """Test 1: Erfolgreiche Suche → list[SearchResult] mit titel/url/snippet."""
        # Mock-Response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Titel 1",
                    "url": "https://example.com/1",
                    "snippet": "Test Snippet 1",
                },
                {
                    "title": "Test Titel 2",
                    "url": "https://example.com/2",
                    "snippet": "Test Snippet 2",
                },
            ]
        }
        mock_get.return_value = mock_response

        results = self.client.search("Test Query", max_results=2)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].titel, "Test Titel 1")
        self.assertEqual(results[0].url, "https://example.com/1")
        self.assertEqual(results[0].snippet, "Test Snippet 1")

    @patch("core.search.searxng_client.requests.get")
    def test_searxng_not_available(self, mock_get):
        """Test 2: SearXNG nicht erreichbar → SearchUnavailableError."""
        mock_get.side_effect = ConnectionError("Connection refused")

        with self.assertRaises(SearchUnavailableError) as context:
            self.client.search("Test Query")

        self.assertIn("nicht erreichbar", str(context.exception))

    @patch("core.search.searxng_client.requests.get")
    def test_max_results_limit(self, mock_get):
        """Test 3: max_results=3 → exakt 3 Ergebnisse (wenn vorhanden)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"title": f"Result {i}", "url": f"https://example.com/{i}", "snippet": f"Snippet {i}"}
                for i in range(10)
            ]
        }
        mock_get.return_value = mock_response

        results = self.client.search("Test Query", max_results=3)

        self.assertEqual(len(results), 3)

    @patch("core.search.searxng_client.requests.get")
    def test_health_check_success(self, mock_get):
        """Test 4: health_check True wenn Server antwortet."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = self.client.health_check()

        self.assertTrue(result)

    @patch("core.search.searxng_client.requests.get")
    def test_health_check_failure(self, mock_get):
        """Test 5: health_check False wenn Server nicht antwortet."""
        mock_get.side_effect = ConnectionError("Connection refused")

        result = self.client.health_check()

        self.assertFalse(result)

    @patch("core.search.searxng_client.requests.get")
    @patch("core.search.searxng_client.WebContentFetcher")
    def test_web_content_fetcher_called(self, mock_fetcher, mock_get):
        """Test 6: WebContentFetcher wird für jede URL aufgerufen."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"title": "Test", "url": "https://example.com/1", "snippet": "Snippet"},
            ]
        }
        mock_get.return_value = mock_response
        mock_fetcher.return_value.fetch.return_value = "Full content"

        results = self.client.search("Test Query", max_results=1)

        self.assertEqual(results[0].inhalt, "Full content")
        mock_fetcher.return_value.fetch.assert_called_once_with("https://example.com/1")


if __name__ == "__main__":
    unittest.main()
